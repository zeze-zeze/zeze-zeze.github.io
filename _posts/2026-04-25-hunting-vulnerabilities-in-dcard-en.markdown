---
layout: post
title: "Throwaway Bugs from Dcard's Bug Bounty"
date: 2026-04-25
lang: en
translation_group: hunting-vulnerabilities-in-dcard
published: false
---

I kept seeing other bug bounty hunters report web issues on X (Twitter) and get paid, which made me a bit envious. Going after targets that are too hard is basically asking to fail, so I picked something from the [HITCON zeroday bug bounty program](https://zeroday.hitcon.org/bug-bounty), landed on Dcard, and found two throwaway issues.

### Insufficient Authorization in Account Recovery Flow

The first issue: after you delete an account, there is a 30-day retention period; if there is no login attempt for 30 days, the account is removed. An attacker can restart that account without knowing the password.

1. Create a user with email and password
2. Delete the user
3. Try to log in to the deleted account with the _wrong_ password, choose to restart the account when prompted, and the restart succeeds

After restart, there is still no password, so the attacker still cannot do much. A bug that can restart someone else’s account looks useless—and in practice I still do not know what it is good for.

<video src="/assets/hunting-vulnerabilities-in-dcard/Insufficient%20Authorization%20in%20Account%20Recovery%20Flow.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br>
### Failure to Invalidate Reset Link After Password Change
The second issue: after a password is updated, the password reset link is still valid.
1. Use “forgot password” to get a reset link, but do not use it yet
2. Change the password in settings while logged in
3. After the change, use the old link to set the password again—it still works

I did not even think of this as a bug at first, but from a bug bounty angle it is still a security issue. The attack scenario in [Reset Password vulnerabilities](https://github.com/0xmaximus/Galaxy-Bugbounty-Checklist/tree/main/Reset%20Password%20vulnerabilities) is: the victim’s change-password link is stolen, the victim then logs in and changes the password, but the attacker can still use the link to take over the account.

<video src="/assets/hunting-vulnerabilities-in-dcard/Failure%20to%20Invalidate%20Reset%20Link%20After%20Password%20Change.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>

<br>
### Reporting to Dcard
Following the [Dcard Hackers](https://www.dcard.tw/hacker) rules, the Dcard Security Team replied with triage in about a day in my experience—very fast—and fixed the issues. Big thumbs up to them.

The hall of fame list was updated; sharing the page with the real pros is more than enough bragging rights for me.

![image](/assets/hunting-vulnerabilities-in-dcard/hacker_board.png)

### On the reward

I actually found a third issue that I think had higher impact, and I provided a practical exploit scenario, but the team treated it as a feature, a known issue to be improved later, so maybe another time.

Even with two throwaways and one “feature” finding, the team said the impact was low and not eligible for a bounty. Because I had three, they said they _might_ combine them for a single payout.

If money actually shows up, I will come back to update the story.
