---
layout: post
title: "How to Use NamedPipeMaster"
date: 2026-04-28
lang: en
translation_group: how-to-use-NamedPipeMaster
---

[NamedPipeMaster](https://github.com/zeze-zeze/NamedPipeMaster) is a tool I made in 2024 that lets you dynamically observe communications over Windows named pipes.

### Environment

Download the ZIP for your OS from the project's [release](https://github.com/zeze-zeze/NamedPipeMaster/releases). The archive contains `Ring3NamedPipeConsumer.exe`, `Ring3NamedPipeMonitor.dll`, and `Ring0NamedPipeFilter.sys`.

Because `Ring0NamedPipeFilter.sys` is not signed (not even with a test signature), loading the driver will fail on systems enforcing driver signature verification.

I normally run this inside a VM and install [VirtualKD-Redux](https://github.com/4d61726b/VirtualKD-Redux). After reboot, press F8 and disable driver signature enforcement so the unsigned driver can be loaded for testing.

If the driver fails to load, running `Ring3NamedPipeConsumer.exe` will print: `[warning] LoadDriver error. Start without Ring0NamedPipeFilter`.

### How to run

Place `Ring3NamedPipeConsumer.exe`, `Ring3NamedPipeMonitor.dll`, and `Ring0NamedPipeFilter.sys` in the same directory. Open a command prompt with Administrator privileges, `cd` to that directory, and run `Ring3NamedPipeConsumer.exe`.

When started you'll see a menu:

```
[1] dump database
[2] start monitor mode
[3] clear database
[4] get database info
[5] filter
[6] inject dll
[7] NamedPipePoker
[8] NamedPipeProxyPoker
[9] NamedPipePoked
[10] help
[11] exit and clean up
```

#### [1] dump database

Dump recorded named pipe events. NamedPipeMaster currently supports five event types:

- CMD_CREATE_NAMED_PIPE: named pipe server created a pipe
- CMD_CONNECT_NAMED_PIPE: named pipe server is waiting for a client to connect
- CMD_CREATE: named pipe client connected to a pipe
- CMD_READ: data read from a named pipe
- CMD_WRITE: data written to a named pipe

#### [2] start monitor mode

Live output of recorded named pipe events.

#### [3] clear database

Clear the recorded named pipe events.

#### [4] get database info

Show statistics about the recorded events:

- total monitoring duration
- number of recorded named pipe events
- which processes produced which named pipes

#### [5] filter

NamedPipeMaster can filter the events you care about:

```
[a] Filter cmdId: all (0=all, 1=CMD_CREATE_NAMED_PIPE, 2=CMD_CREATE, 3=CMD_READ, 4=CMD_WRITE, 5=CMD_CONNECT_NAMED_PIPE)
[b] Filter sourceType: all (0=all, 1=SOURCE_MINIFILTER, 2=SOURCE_INJECTED_DLL)
[c] Filter processId: all (0=all)
[d] Filter imagePath: %%
[e] Filter fileName: %%
[f] Filter canImpersonate: all (0=all, 1=yes)
[g] Reset filter
```

- [a] Filter cmdId: record only selected event types
- [b] Filter sourceType: choose the event source. Events can come from the driver (minifilter) or from the injected DLL. If the driver is loaded you will receive system-wide events from the driver; the DLL produces events only for processes where it has been injected. Choose SOURCE_MINIFILTER to receive only driver events, or SOURCE_INJECTED_DLL to receive only events from injected processes.
- [c] Filter processId: record events only for a specific PID
- [d] Filter imagePath: record events only when the process image path contains the specified substring
- [e] Filter fileName: record events only when the named pipe name contains the specified substring
- [f] Filter canImpersonate: record events only when impersonation is possible
- [g] Reset filter: reset all filters

#### [6] inject dll

Inject `Ring3NamedPipeMonitor.dll` into a target process. Compared to `Ring0NamedPipeFilter.sys`, the injected DLL adds:

- a check when a named pipe server accepts a client connection to determine whether the client can impersonate
- a call stack printout for captured events, which helps quickly locate the code that triggered the named pipe event when reverse-engineering

#### [7] NamedPipePoker

Act as a named pipe client and actively connect to a named pipe server. Enter the pipe name in the form `\\.\\pipe\\<pipename>`.

If the connection succeeds you'll get an interactive read/write interface:

```
NPM-CLI> 7
pipe name: \\.
\pipe\<pipename>

    [a] Write data (alive: yes)
    [b] Read data (total 0 data)
    [c] Test impersonation
    [d] exit

    choice:
```

- [a] Write data: send arbitrary data to the named pipe server
- [b] Read data: receive data from the named pipe server
- [c] Test impersonation: only useful for option [9] NamedPipePoked
- [d] exit: leave the interactive interface

This is useful to quickly trigger named pipe events on a target server so NamedPipeMaster can capture them.

#### [8] NamedPipeProxyPoker

Inject `Ring3NamedPipeMonitor.dll` into a target PID and make that process act as the named pipe client when connecting to the target server.

```
NPM-CLI> 8
target pid: <pid>
target pipe name: \\\\.
\\pipe\\<pipe name>
Inject pid <pid> successfully.

    [a] Write data (alive: yes)
    [b] Read data (total 0 data)
    [c] Test impersonation
    [d] exit

    choice:
```

The interactive interface is the same as [7]. The difference is the server will see the injected target process as the client. This is handy for bypassing checks that validate the client's signature or image path.

#### [9] NamedPipePoked

Act as a named pipe server and wait for a client to connect.

```
NPM-CLI> 9
pipe name: \\\\.
\\pipe\\<pipe name>

    [a] Write data (alive: no)
    [b] Read data (total 0 data)
    [c] Test impersonation
    [d] exit

    choice:
```

The interactive interface is similar to [7], but option [c] Test impersonation will check whether the connected client can be impersonated.

This mode is useful when you know how to trigger the client to connect — you can impersonate a client to the target server.

#### [10] help

Show the help menu.

#### [11] exit and clean up

Exit NamedPipeMaster. The driver will be unloaded, but any processes where `Ring3NamedPipeMonitor.dll` was injected will not be restarted.
