---
layout: post
title:  "A Throwaway Bug in Process Explorer"
date:   2026-04-26
lang: en
translation_group: process-explorer-long-name-minidump
---

Process Explorer is part of [Sysinternals](https://learn.microsoft.com/en-us/sysinternals/); a huge number of people use it. I usually do not have the courage to go after a target that big.

At Black Hat Asia, [Or Yair](https://x.com/oryair1999) presented [A HACKER'S MAGIC SHOW OF DİSAPPEARING DOTS AND SPACES](https://i.blackhat.com/Asia-24/Presentations/Asia-24-Yair-magicdot-a-hackers-magic-show-of-disappearing-dots-and-spaces.pdf), including a fun Process Explorer issue, so I wanted to follow a similar line of research.

![image](/assets/Process-Explorer-Long-Process-Name-Minidump-Crash/slides_1.png)

<br>
### CVE-2023-42757
Or Yair’s issue was: when Process Explorer shows the process name, it appends `(<pid>)` to the name, but the buffer is only 256 bytes, so a 255-byte process name means appending the PID and then calling `wcscpy_s` overflows the buffer you promised.

![image](/assets/Process-Explorer-Long-Process-Name-Minidump-Crash/wcscpy_s.png)

You still cannot really exploit it: `wcscpy_s` is a [security-enhanced CRT function](https://learn.microsoft.com/en-us/cpp/c-runtime-library/security-enhanced-versions-of-crt-functions?view=msvc-170). On overflow the error path runs `_invoke_watson`, the app exits, and a minidump is produced, so the effect is at best a crash.

<br>
### What I found
If Or Yair’s CVE-2023-42757 is “anti-analysis,” mine is more like “anti-dump.”

Same root cause, different path: if you right-click and choose `Create Minidump` or `Create Full Dump` for a very long process name, the same buffer is exceeded and the process exits.

<video src="/assets/Process-Explorer-Long-Process-Name-Minidump-Crash/demo.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br>
I did not start the test process with a double-click; I used the low-level NT API [`NtCreateUserProcess`](https://gist.github.com/zeze-zeze/b5b2e12944c3e6003db4a4c473d3970c), or process creation would fail.

### MSRC
They said it is fixed, but there was no CVE, and a bug this low-impact will not get a bounty, obviously.

```
Hello Zeze,
 
Thank you for your submission - we have marked this as a Low Severity vulnerability and our EG team has fixed it.
 
The current rationale is:
 
"This is a local DoS affecting current versions of Process Explorer. Finder demonstrates the ability to crash Process Explorer when attempting to create a minidump of a process with a long name (255 characters)."
 
Thank you,
MSRC
```
