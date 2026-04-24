---
layout: post
title:  "在 Process Explorer 找到的廢洞"
date:   2026-04-24
translation_group: process-explorer-long-name-minidump
---

Process Explorer 身為 [Sysinternals](https://learn.microsoft.com/en-us/sysinternals/) 中的元件，有著不計其數的使用者，混子通常是沒勇氣挑戰的。

不過大哥 [Or Yair](https://x.com/oryair1999) 在 Blackhat Asia 發表了 [A HACKER'S MAGİC SHOW OF DİSAPPEARING DOTS AND SPACES](https://i.blackhat.com/Asia-24/Presentations/Asia-24-Yair-magicdot-a-hackers-magic-show-of-disappearing-dots-and-spaces.pdf)，其中提到了 Process Explorer 的漏洞感覺很有趣，就想嘗試跟上大哥的腳步。

![image](/assets/Process-Explorer-Long-Process-Name-Minidump-Crash/slides_1.png)

<br>
### CVE-2023-42757
Or Yair 找到的問題是在 Process Explorer 顯示 process name 時會在後面 append `(<pid>)`，但是 buffer size 又只有給 256 bytes，所以只要 process name 設 255 bytes，那在 append pid 之後呼叫 wcscpy_s 時就會超出給定的 buffer size。

![image](/assets/Process-Explorer-Long-Process-Name-Minidump-Crash/wcscpy_s.png)

但是這個漏洞無法 exploit，因為 wcscpy_s 是 [Security-enhanced versions of CRT functions](https://learn.microsoft.com/en-us/cpp/c-runtime-library/security-enhanced-versions-of-crt-functions?view=msvc-170)，在發現 buffer overflow 時會觸發 error handler 呼叫 `calls _invoke_watson`，然後應用程式就會關閉並產生 minidump，所以頂多造成 crash。

<br>
### 我找的漏洞
如果說 Or Yair 的 CVE-2023-42757 效果是 anti analysis 的話，那我的就是 anti dump。

同個 root cause，只是觸發點在按右鍵 `Create Minidump` 或 `Create Full Dump` 想產生很長的 process name 的 dump 時就會超出給定的 buffer size 而關閉。

<video src="/assets/Process-Explorer-Long-Process-Name-Minidump-Crash/demo.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br>
影片中建立 process 的方式不是直接點兩下，而是用底層 NTAPI [NtCreateUserProcess](https://gist.github.com/zeze-zeze/b5b2e12944c3e6003db4a4c473d3970c)，不然 process 會建立失敗。

### 回報 MSRC
總之說是修好了，但是 CVE 沒發，當然這種廢洞也不可能有獎金 🫠

```
Hello Zeze,
 
Thank you for your submission - we have marked this as a Low Severity vulnerability and our EG team has fixed it.
 
The current rationale is:
 
"This is a local DoS affecting current versions of Process Explorer. Finder demonstrates the ability to crash Process Explorer when attempting to create a minidump of a process with a long name (255 characters)."
 
Thank you,
MSRC
```