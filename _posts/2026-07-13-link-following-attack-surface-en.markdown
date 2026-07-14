---
layout: post
title: "Understanding the Windows Link-Following Attack Surface"
date: 2026-07-13
lang: en
translation_group: windows-link-following-attack-surface
---

## Important Basics of Windows Link Following

### Junction

A junction points one directory to another directory, letting you access a folder that is actually stored somewhere else. It has been supported since Windows 2000.

Effect: when you access something inside the junction, you are really accessing the contents of the target directory.

How to create one:

```
mklink /J <link> <target>
```

Or use [CreateMountPoint from symboliclink-testing-tools](https://github.com/googleprojectzero/symboliclink-testing-tools/tree/main/CreateMountPoint):

```
CreateMountPoint.exe "junction_rpc_control" "\RPC CONTROL\\"
```

### Symbolic Link

A symbolic link can point to either a file or a directory, and it supports cross-volume and network paths. It is used for path redirection that behaves like a file or directory. It has been supported since Windows Vista.

Creating a regular file symbolic link normally requires the Administrator-only [SeCreateSymbolicLinkPrivilege](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/security-policy-settings/create-symbolic-links). However, some Object Manager namespaces such as `\RPC CONTROL\` can still be used by a normal user.

Effect: any file operation performed on the symbolic link is actually performed on its target.

How to create one: use [CreateNativeSymLink from symboliclink-testing-tools](https://github.com/googleprojectzero/symboliclink-testing-tools/tree/main/NativeSymlink):

```
CreateNativeSymlink.exe "\RPC CONTROL\trick.txt" "\??\c:\other_file"
```

### Attack Method

1. Set `Dir` to be a junction pointing to `\RPC CONTROL\`
2. Set `\RPC CONTROL\file.txt` to be a symbolic link pointing to the target file `other\stuff.any`
3. When a program tries to delete `\Dir\file.txt`, the file that really gets deleted is `other\stuff.any`

![image.png](/assets/windows-link-following-attack-surface/image.png)

<br/>

## Attack Scenarios
### Arbitrary File Delete

If you know that a program will delete a file inside a directory, and both that directory and file are attacker-controlled from a low-privilege context, you can swap the directory for a junction to `\RPC CONTROL\` before the deletion happens, then make `\RPC CONTROL\target_file` a symbolic link to some other file. When the program deletes the target file, it actually deletes the other file instead.

<video src="/assets/windows-link-following-attack-surface/junction_rpc_control.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br/>

### Expanding the Scenario with Oplocks

A program will typically enumerate the files in `C:\target_dir` before operating on one of them. If, as in an “Arbitrary File Delete” attack, we preconfigure a junction to point directly to `\RPC Control\`, the enumeration will fail because `\RPC Control\` is an Object Manager namespace and cannot be enumerated using ordinary filesystem directory-enumeration APIs. If enumeration fails, the program may simply abort the deletion. Therefore, the junction and symbolic link cannot be set up in advance.

An oplock can solve this problem: it allows the program to enumerate the directory successfully, while also making it possible, after enumeration, to cause the subsequent deletion operation to target a file chosen by the attacker.

Once a file is oplocked, other operations that try to access the same file will block until the oplock is released. Oplocks have existed since Windows NT 3.1.

How to create one: use [SetOpLock from symboliclink-testing-tools](https://github.com/googleprojectzero/symboliclink-testing-tools/tree/main/SetOpLock):

```
SetOplock.exe C:\target_file rwdx
```

<video src="/assets/windows-link-following-attack-surface/SetOpLock.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br/>

### Attack Flow

First, place an oplock on `C:\target_dir\target_file`. When the program tries to operate on `target_file`, it gets blocked. During that window, turn `C:\target_dir` into a junction to `\RPC CONTROL\`, and make `\RPC CONTROL\target_file` a symbolic link to another file.

<br/>

## Exploit
### From Arbitrary File Delete to Arbitrary Directory Delete

You can use the file-deletion APIs below to delete `C:\Config.Msi::$INDEX_ALLOCATION`, which turns an arbitrary file delete into an arbitrary directory delete.

- `del` fails here
- Windows API [DeleteFile](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-deletefile)
- C++ [std::filesystem::remove](https://en.cppreference.com/w/cpp/filesystem/remove)

Note: this trick no longer works on the latest Windows 11 24H2 builds because deleting `$INDEX_ALLOCATION` fails there, but it still works on the latest Windows 11 23H2 builds.

Implementation: [ZDI's FolderContentsDeleteToFolderDelete](https://github.com/thezdi/PoC/tree/main/FilesystemEoPs/FolderContentsDeleteToFolderDelete)

```
FolderContentsDeleteToFolderDelete.exe /target <TARGET_DIR> /initial <INITIAL_DIR>
```

<video src="/assets/windows-link-following-attack-surface/FolderContentsDeleteToFolderDelete.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br/>

### From Arbitrary Directory Delete to Privilege Escalation

For the underlying idea, see [Abusing Arbitrary File Deletes to Escalate Privilege and Other Great Tricks](https://www.zerodayinitiative.com/blog/2022/3/16/abusing-arbitrary-file-deletes-to-escalate-privilege-and-other-great-tricks). For an implementation, see [ZDI's FolderOrFileDeleteToSystem](https://github.com/thezdi/PoC/tree/main/FilesystemEoPs/FolderOrFileDeleteToSystem).

#### stage 1
1. Run an MSI package as a normal user. During install it writes a file and then triggers the uninstaller.
2. During uninstall, the file to be deleted is first written into an `.rbf` file under `C:\Config.Msi`. That `.rbf` file inherits the original file's DACL, so at this point the attacker can grab a handle to the `.rbf` file and prevent `C:\Config.Msi` from being deleted.
3. Because of that, the registry key under `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\Folders` that proves `C:\Config.Msi` is legitimate is also not deleted.
4. The attacker then uses the arbitrary directory delete bug to delete `C:\Config.Msi` and recreate it as a low-privilege directory, obtaining a handle to that directory.

#### stage 2
1. Run the MSI a second time. After the installer finishes, `C:\Config.Msi` becomes a high-privilege directory again, but because the attacker already holds a handle, the directory can still be manipulated and turned back into a low-privilege directory.
2. The attacker overwrites the `.rbs` and `.rbf` files inside `C:\Config.Msi`. These are the files the uninstaller uses to determine what should be rolled back.
3. The attacker intentionally makes the MSI fail with `ErrorOut` to trigger rollback.
4. During rollback, the `.rbs` script is executed and the `.rbf` file is restored.

Following [Wh04m1001/IFaultrepElevatedDataCollectionUAC](https://github.com/Wh04m1001/IFaultrepElevatedDataCollectionUAC), you can use the project's `cmd.rbs` and tamper with the original `.rbs` when creating the fake `C:\Config.Msi`, causing `cmd.exe` to run with high privileges.

Also see [How can I develop my .rbs file?](https://github.com/Wh04m1001/IFaultrepElevatedDataCollectionUAC/issues/1). You can build an MSI with [Advanced Installer](https://www.advancedinstaller.com/), set the rollback action to `cmd.exe`, and the corresponding `.rbs` will be generated when the MSI is built.

<video src="/assets/windows-link-following-attack-surface/FolderOrFileDeleteToSystem.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br/>

## Choosing a Target
This attack surface is extremely powerful, and also very easy to get wrong. Who would expect that even deleting a file through normal Windows APIs could turn into a security issue?

Other researchers have already used this technique against antivirus products:

- Avira: [Vulnerability in Avira Security Suite enables for privilege escalation attacks](https://www.sidechannel.blog/en/vulnerability-in-avira-security-suite-enables-for-privilege-escalation-attacks/)
- Windows Defender: [Follow the Link: Exploiting Symbolic Links with Ease](https://www.cyberark.com/resources/threat-research-blog/follow-the-link-exploiting-symbolic-links-with-ease)
- ESET, Avast, AVG, F-Secure, VIPRE, WithSecure: [Breaking Barriers and Assumptions: Techniques for Privilege Escalation on Windows: Part 2](https://www.zerodayinitiative.com/blog/2024/7/30/breaking-barriers-and-assumptions-techniques-for-privilege-escalation-on-windows-part-2)

So I picked a program that deletes files where both the file and its parent directory are attacker-controlled, such as a cleanup tool. I will use [CCleaner](https://www.ccleaner.com/ccleaner/download) as the example because it is fairly well known in Taiwan.

### CCleaner

We all know cleanup tools remove files they consider unnecessary. One common target is `C:\Windows\Temp`, because many applications store temporary files there.

That creates a problem:
1. `C:\Windows\Temp` is writable by any user. If CCleaner deletes files there without checking whether the file is attacker-controlled, or without first locking the file it is about to delete,
2. an attacker can create a directory under `C:\Windows\Temp`, put a file inside it, and place an oplock on that file,
3. when CCleaner deletes that attacker-created file, the oplock triggers, and during that pause the attacker can replace the directory being deleted with a junction to `\RPC CONTROL\` and set `\RPC CONTROL\target_file` as a symbolic link to the `C:\Config.Msi` directory,
4. then use the earlier **arbitrary file delete to arbitrary directory delete** and **arbitrary directory delete to privilege escalation** exploit chain to finish the escalation.

I reported the bug to ZDI and eventually received [CVE-2025-3025](https://www.zerodayinitiative.com/advisories/ZDI-25-905/) plus a pocket-money-tier bounty.


## Defenses

The exact defense depends on things like supported Windows versions, performance constraints, and how the product is used. These are a few defenses I saw while researching this attack surface:

- Hold a handle to the parent directory while deleting the file, so other processes cannot write to or delete from it.
- Microsoft provides [PROCESS_MITIGATION_POLICY](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-process_mitigation_policy), including [ProcessRedirectionTrustPolicy](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-process_mitigation_policy), which a process can enable through [SetProcessMitigationPolicy](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessmitigationpolicy) so opening a symbolic link for deletion fails.
  Supported on Windows 8 and later.
- `NtCreateFile` has a `FILE_COMPLETE_IF_OPLOCKED` option. If the target file is already oplocked, the call returns immediately. If it is not, the process can oplock the file itself and only delete it after that succeeds.
