---
layout: post
title: "認識 Windows Link Following 攻擊面"
date: 2026-07-13
translation_group: windows-link-following-attack-surface
---

大哥一般是特別 C，能帶我們躺著研究的角色；乾爹則是提供研究員 credit、bounty 等好處的角色。大哥與乾爹的角色不衝突，可以同時擔任，ZDI 就是其中一個很好的例子。

ZDI 除了主辦白帽駭客的最高殿堂 - [Pwn2Own](https://www.zerodayinitiative.com/blog/tag/Pwn2Own) 之外，也會收購第三方產品的漏洞，雖然不是任何產品、任何漏洞都收，但是根據 [Published Advisories](https://www.zerodayinitiative.com/advisories/published/)，收購的漏洞量也是十分驚人，是個不折不扣的乾爹。另外，ZDI 的研究員也會擔起大哥的責任，分享研究成果到他們的 [Blog](https://www.zerodayinitiative.com/blog/)，許多 bug bounty hunter 會研讀他們的研究成果，並把學到的知識再拿去找漏洞，形成一個良性循環。

我要分享我讀 ZDI 的文章後，把學習到的知識應用到實戰，再回報漏洞給 ZDI 的經驗。

## Windows Link Following 重要基本知識

### Junction

Junction (連接點) 將一個目錄指向另一個目錄，存取實際存放在其他位置的資料夾。windows 2000 開始支援。

效果：在存取這個 junction 中的東西時，實際上會存取到指向的目錄中的東西

建立方法：

```
mklink /J <link> <target>
```

或是用 [symboliclink-testing-tools 的 CreateMountPoint](https://github.com/googleprojectzero/symboliclink-testing-tools/tree/main/CreateMountPoint)

```
CreateMountPoint.exe "junction_rpc_control" "\RPC CONTROL\\"
```

### Symbolic Link

Symbolic Link（符號連結）可以指向檔案或目錄，並支援跨分割區、網路路徑。用於模擬檔案和目錄，做路徑重導向。Windows Vista 開始支援。

一般檔案的 symbolic link 需要 Administrator 才有的 [SeCreateSymbolicLinkPrivilege](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/security-policy-settings/create-symbolic-links) 權限才能建立，但是一些 Object Manager 如 `\RPC CONTROL\` 可以由一般使用者權限建立。

效果：在對 symbolic link 做任何檔案操作時，實際上會操作到指向的檔案

建立方法：用 [symboliclink-testing-tools 的 CreateNativeSymLink](https://github.com/googleprojectzero/symboliclink-testing-tools/tree/main/NativeSymlink) 建立 symlink

```
CreateNativeSymlink.exe "\RPC CONTROL\trick.txt" "\??\c:\other_file"
```

### 攻擊原理

1. 設定 `Dir` 為一個 junction 指向 `\RPC CONTROL\`
2. 設定 `\RPC CONTROL\file.txt` 為一個 symbolic link 指向目標檔案 `other\stuff.any` 
3. 當程式嘗試刪除 `\Dir\file.txt` 時，實際上被刪除的是 `other\stuff.any` 

![image.png](/assets/windows-link-following-attack-surface/image.png)

<br/>

## 攻擊情境

### 任意刪除檔案

只要能知道一個程式會刪除某個目錄中的檔案，並且那個目錄、檔案是低權限使用者可控的，就可以在程式刪除目標檔案前，把目錄改成 junction 指向 `\RPC CONTROL\` ，並設定 `\RPC CONTROL\target_file` 為一個 symbolic link 指向另一個檔案。這樣當程式刪除目標檔案時，實際上會刪除另一個檔案。

<video src="/assets/windows-link-following-attack-surface/junction_rpc_control.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br/>

### 擴大攻擊情境 by Oplock

通常程式會先確認有哪些檔案在 `C:\target_dir` 才去操作檔案，如果直接像是「任意刪除檔案」中設定 junction 指向 `\RPC CONTROL\`，會因為 `\RPC CONTROL\` 是一個 Object Manager namespace 而無法用一般列舉目錄的 API 直接列舉檔案，列舉失敗也許程式就不刪除了，所以無法提前設定 junction 和 symbolic link。

Oplock 可以解決這個問題，既滿足讓程式列舉目錄時可以成功，又能讓程式在列舉之後刪除檔案時，刪除到攻擊者指定的檔案。

Oplock：當檔案被 oplock 後，其他要存取同個檔案的操作會被卡住，直到 oplock 被釋放。Windows NT3.1 開始支援。

建立方法：用 [symboliclink-testing-tools 的 SetOpLock](https://github.com/googleprojectzero/symboliclink-testing-tools/tree/main/SetOpLock) 建立 oplock

```
SetOplock.exe C:\target_file rwdx
```

<video src="/assets/windows-link-following-attack-surface/SetOpLock.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br/>

### 攻擊方法
先 Oplock `C:\target_dir\target_file` ，在程式嘗試操作 `target_file` 時會被卡住，趁這個時候設定 `C:\target_dir` 為 junction 指向 `\RPC CONTROL\` 、 `\RPC CONTROL\target_file` 為 symbolic link 指向另一個檔案。

<br/>

## Exploit

### 從任意刪除檔案到任意刪除目錄

用 Windows API [DeleteFile](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-deletefile) 刪除 `C:\Config.Msi::$INDEX_ALLOCATION` 來刪除目錄。

Note: 這招在 windows 11 24H2 最新版用不了 (刪除 $INDEX_ALLOCATION 會失敗)，但 windows 11 23H2 最新版可以用。

用 [ZDI 的 FolderContentsDeleteToFolderDelete](https://github.com/thezdi/PoC/tree/main/FilesystemEoPs/FolderContentsDeleteToFolderDelete) 實作

```
FolderContentsDeleteToFolderDelete.exe /target <TARGET_DIR> /initial <INITIAL_DIR>
```

<video src="/assets/windows-link-following-attack-surface/FolderContentsDeleteToFolderDelete.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br/>

### 從任意刪除目錄到提權

原理參考 [Abusing Arbitrary File Deletes to Escalate Privilege and Other Great Tricks](https://www.zerodayinitiative.com/blog/2022/3/16/abusing-arbitrary-file-deletes-to-escalate-privilege-and-other-great-tricks)，實作參考 [ZDI 的 FolderOrFileDeleteToSystem](https://github.com/thezdi/PoC/tree/main/FilesystemEoPs/FolderOrFileDeleteToSystem)

#### stage 1
1. 用一般使用者 執行 msi 檔案，install 時寫入一個檔案，然後觸發 uninstaller
2. uninstaller 在解安裝時會把要刪除的檔案先寫在 `C:\Config.msi` 的 rbf 檔案中，其中這個 rbf 檔案的 DACL 跟原本的檔案相同，所以攻擊者這時可以拿取 rbf 檔案的 handle，避免 `C:\Config.msi` 被刪除
3. 原本寫在 registry `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Installer\Folders` 中用來確認 `C:\Config.msi` 合法性的 key 也因此沒被刪除
4. 這時攻擊者利用任意刪除目錄的漏洞刪除 `C:\Config.msi`，並建立一個低權限的 `C:\Config.msi`，攻擊者這時取得這個目錄的 handle

#### stage 2
1. 再執行一次 msi 檔案，跑完 installer，這時 `C:\Config.msi` 會被改寫成高權限目錄，但因為這時攻擊者已經有 handle 了，所以還是可以操作目錄，把它改寫成低權限目錄
2. 攻擊者改寫 `C:\Config.msi` 中的 rbs、rbf 檔案，這是 uninstaller 用來辨別要 rollback 哪些東西的檔案
3. 攻擊者故意讓 msi 檔案出錯 `ErrorOut`，觸發 rollback
4. rollback 時會執行 .rbs 並把 .rbf 還原

參考 [Wh04m1001/IFaultrepElevatedDataCollectionUAC](https://github.com/Wh04m1001/IFaultrepElevatedDataCollectionUAC)，使用專案中的 cmd.rbs，在建立偽造的 `C:\Config.Msi` 時竄改原本的 .rbs 檔，以高權限執行 cmd.exe。

參考 [How can I develop my .rbs file?](https://github.com/Wh04m1001/IFaultrepElevatedDataCollectionUAC/issues/1)，可以用 [Advanced Installer](https://www.advancedinstaller.com/) 建立 .msi，其中設定 rollback action 為 cmd.exe，在執行產生 .msi 時就會產生對應的 .rbs

<video src="/assets/windows-link-following-attack-surface/FolderOrFileDeleteToSystem.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br/>

## 挑選目標
這個攻擊面太強大了，而且非常容易犯錯，誰想得到都用 Windows API 刪除檔案還會出事？

之前已經有其他研究員用這招在找防毒軟體的漏洞

- Avira: [Vulnerability in Avira Security Suite enables for privilege escalation attacks](https://www.sidechannel.blog/en/vulnerability-in-avira-security-suite-enables-for-privilege-escalation-attacks/)
- Windows Defender: [Follow the Link: Exploiting Symbolic Links with Ease](https://www.cyberark.com/resources/threat-research-blog/follow-the-link-exploiting-symbolic-links-with-ease)
- ESET、Avast、AVG、F-Secure、VIPRE、WithSecure: [Breaking Barriers and Assumptions: Techniques for Privilege Escalation on Windows: Part 2](https://www.zerodayinitiative.com/blog/2024/7/30/breaking-barriers-and-assumptions-techniques-for-privilege-escalation-on-windows-part-2)

所以我選了一個會刪除檔案的程式，並且刪除的檔案和所在目錄是攻擊者可控的，例如清理垃圾程式。
以下拿台灣人相對普遍認識的 [CCleaner](https://www.ccleaner.com/ccleaner/download) 為例。

### CCleaner
我們都知道垃圾清理程式會把系統中它認為不需要的檔案刪除，其中 `C:\Windows\Temp` 就是垃圾清理程式的一個目標，因為許多應用程式會把它們的暫存檔寫到這個地方。

這邊就存在一個問題，
1. 由於 `C:\Windows\Temp` 是任何使用者都可以寫入的目錄，假如 CCleaner 在刪除 `C:\Windows\Temp` 沒有檢查刪除的檔案是不是攻擊者可控，或是沒有在刪除之前先鎖住這個要刪除的檔案
2. 攻擊者就能先在 `C:\Windows\Temp` 建立一個目錄，裡面放一個檔案，並對這個檔案設定 oplock
3. CCleaner 刪除攻擊者建的檔案時就會觸發 oplock，攻擊者趁這時把要被刪除的目錄改成 junction 指向 `\RPC CONTROL\`，並設定 `\RPC CONTROL\target_file` 為一個 symbolic link 指向 `C:\Config.MSI` 目錄
4. 再利用前面提到的**從任意刪除檔案到任意刪除目錄**、**從任意刪除目錄到提權** exploit chain 完成提權。

最後回報漏洞給 ZDI 並取得 [CVE-2025-3025](https://www.zerodayinitiative.com/advisories/ZDI-25-905/) 與零用錢等級的賞金。


## 防禦方法

防禦方法可以根據產品的目標系統版本，考量效能與使用情境等因素用不同方法實作，以下分享我在研究這個攻擊面時看到的產品的防禦方法。

- 在刪除檔案時咬住上一層目錄的 handle，不讓其他 process 寫入或刪除
- 微軟有提供 [PROCESS_MITIGATION_POLICY](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-process_mitigation_policy) 的 [ProcessRedirectionTrustPolicy](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ne-winnt-process_mitigation_policy)，讓 process 透過 [SetProcessMitigationPolicy](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessmitigationpolicy) 在刪除 symbolic link 時開檔失敗
    - windows 8 以後支援
- NtCreateFile 有 FILE_COMPLETE_IF_OPLOCKED 選項，如果目標檔案被 Oplock 就會直接 return。如果檔案沒被 oplock，則對這個檔案設 oplock，成功之後才刪除這個檔案