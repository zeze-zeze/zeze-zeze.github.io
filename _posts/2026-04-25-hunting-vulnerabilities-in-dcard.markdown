---
layout: post
title:  "在 Dcard 的 Bug Bounty 找到的廢洞"
date:   2026-04-25
translation_group: hunting-vulnerabilities-in-dcard
---

作為一個成熟的混子，雖然技術跟不上，理解力也一般，但是我們有自知之明，選擇一個合適的目標才不會讓自己太快放棄。

在 X (twitter) 上一直看到其他 bug bounty hunter 回報 web 漏洞拿獎金很羨慕，不過混子挑戰太難的目標無疑是飛蛾撲火，所以從 [hitcon zeroday 的 bounty program](https://zeroday.hitcon.org/bug-bounty) 隨便找了一個目標看看，然後就選中 Dcard，最後找到兩個廢洞。

### Insufficient Authorization in Account Recovery Flow
第一個漏洞是在刪除帳號後會有 30 天保留時間，如果 30 天都沒有嘗試登入就會刪除。攻擊者可以在不知道這個帳號的密碼的情況下，重啟這個帳號。
1. 用信箱、密碼建立使用者
2. 刪除使用者
3. 用錯誤的密碼嘗試登入被刪除的使用者，跳出是否重啟帳號，按是成功重啟

不過重啟後因為沒密碼所以也不能做什麼，所以能幫別人重啟帳號的漏洞看似沒用，實則還真的不知道能拿來做什麼。

<video src="/assets/hunting-vulnerabilities-in-dcard/Insufficient%20Authorization%20in%20Account%20Recovery%20Flow.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br>
### Failure to Invalidate Reset Link After Password Change
第二個漏洞是密碼更新後，密碼重設連結還未失效
1. 用忘記密碼取得更改密碼的連結，但先別用
2. 在登入後的設定中更改密碼
3. 更改密碼後再用剛剛的連結更改密碼，仍然能更改成功

本來不覺得這會是個漏洞，但以 bug bounty 的角度來看似乎仍然是安全問題。參考 [Reset Password vulnerabilities](https://github.com/0xmaximus/Galaxy-Bugbounty-Checklist/tree/main/Reset%20Password%20vulnerabilities) 中寫的攻擊情境是受害者的更改密碼連結被攻擊者用某種方式竊取，後來受害者覺得可能怪怪的，所以登入後修改自己的密碼，但改完密碼之後攻擊者卻還是能用連結改密碼。

<video src="/assets/hunting-vulnerabilities-in-dcard/Failure%20to%20Invalidate%20Reset%20Link%20After%20Password%20Change.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br>
### 回報 Dcard
依照 [Dcard Hackers](https://www.dcard.tw/hacker) 規則回報漏洞之後，Dcard Security Team 都在一天左右回覆漏洞的評估結果，在我的經驗中算非常非常快，也積極修復漏洞，必須給 Dcard Security Team 一個讚！

漏洞列表也更新了，能跟大佬們同框夠我吹十年了。

![image](/assets/hunting-vulnerabilities-in-dcard/hacker_board.png)


### 關於獎金
其實我還找了第三個漏洞，個人認為危害較大，並且我也提出了可實際利用的攻擊情境，不過 Dcard Security Team 說這是 feature，當作 known issue 處理，但未來會針對這部分進行調整，所以之後有機會再分享。

雖然找到有兩個廢洞跟一個 feature，Dcard Security Team 說漏洞危害較低，不符合獎金資格。不過因為找了三個，所以被告知可能可以三個合併算獎金。

如果真拿到錢，我再回來還願。