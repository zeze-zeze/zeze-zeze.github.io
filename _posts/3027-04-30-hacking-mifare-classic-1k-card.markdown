---
layout: post
title: "揭開 Mifare Classic 1k 卡的真面目"
date: 3027-04-30
translation_group: hacking-mifare-classic-1k-card
---

作為一個成熟的混子，分辨真大哥是第一要務。不能因為別人認為他是大哥，就盲從相信他就是大哥。

## 研究動機

2025 在 HITCON 活動組本來到六月都在滑水，因為入坑 PCB Badge 燒太多時間、Re:CTF 去年做過所以想做做其他的、要炒前年釣魚牆的冷飯又有點不願意。

剛好六月中悠遊卡被高中生破解的新聞，例如[全台首例！悠遊卡編碼 遭高中生自學破解](https://www.youtube.com/watch?v=wpsiPb0RLaI)，網路上各種新聞和專家都在說這很簡單，讓還不會的我有點羞愧。不過想說應該不會只有我不會，所以才決定蹭熱度開 NFC Hacking 這個活動科普相關知識，也還好沒因為時間太晚而被拒絕加入活動。

不過學了才知道要做到竄改悠遊卡確實挺容易的，就是把工具買一買，破解程式裝一裝，照著教學做就可以改卡裡的值了。但其實破解 Mifare Classic 1K 卡是循序漸進的，前前後後好幾篇論文在嘗試破解，最後終於找到一個穩定且快速的做法能把卡片的 key 破解完。

而破解的原理還是跟密碼學脫離不了關係，出現密碼學就代表會出現很多數學，要完全理解還是得花不少時間。

### NFC 安全相關閱讀

- NFC security: 10 security risks you need to know: https://nordvpn.com/zh-tw/blog/nfc-security/

#### 詐騙手法

- 新型 NFC 惡意程式鎖定 Android 用戶 竊取銀行資訊: https://www.informationsecurity.com.tw/article/article_detail.aspx?aid=11209

#### 相關專案

- securenetwork/NFCulT: https://github.com/securenetwork/NFCulT

### 竄改 / 破解悠遊卡 / Mifare 資源

- MIFARE Classic: Completely Broken: https://hitcon.org/download/2010/11_MIFARE%20Classic%20IS%20Completely%20BROKEN.pdf
- 晶片卡弱點分析 MIFARE, ATM Card & 花博門票: https://hitcon.org/download/2010/9_%E6%99%B6%E7%89%87%E5%8D%A1%E5%AE%89%E5%85%A8%E6%80%A7%E6%8E%A2%E8%A8%8E.pdf
- FuzzySecurity RFID 系列教程 (Appendix A, Part 1-4): https://fuzzysecurity.com/tutorials/rfid/
- NFC 資安實戰 - 興大資訊社社課: https://taichunmin.idv.tw/blog/2022-12-12-nchuit-nfc.html

#### Proxmark3 — 常用備忘

刷韌體與初次連線常見步驟（參考 Getting started with the proxmark3 easy）：如果在執行完 ./pm3-flash-bootrom 後出現紅燈且主機偵測不到，可按板上的按鈕再試一次。

常見命令（在 proxmark3 shell 或 pm3 工具中執行）：

讀 UID:

```
[usb] pm3 --> hf 14a read
[+]  UID: CB 6E 94 AD
[+] ATQA: 00 04
[+]  SAK: 08 [2]
```

爆破 Mifare Classic 1 的 key（會產生整張卡的 dump；note: 無法對 Mifare EV1 進行此爆破）：

```
hf mf autopwn
```

把 dump 寫入另一張卡:

```
hf mf cload -f binary.dmp
```

確認卡片 type:

```
hf search
```

取得 Mifare 卡的資訊:

```
hf mf info
```

寫入 uid、atqa、sak（小心：寫錯可能毀卡）:

```
hf mf csetuid -u E184A334 --atqa 0004 --sak 08
```

讀取第 0 個 block:

```
hf mf rdbl --blk 0
```

強制寫入第 0 個 block（危險：第 5 個 byte 為 BCC，錯誤會使卡失效）:

```
hf mf wrbl --blk 0 -d E184A334f20804000237F710ABE4451D --force
```

有 key 檔就可以直接 restore 所有卡片資訊:

```
hf mf restore -f hf-mf-02805D8A-dump.bin -k hf-mf-02805D8A-key.bin
```

### Mifare Classic 1K（示意圖）

![Mifare Classic 1K 示意圖](https://hackmd.io/_uploads/BJsfY-3Bgl.png)

## 破解原理（簡潔整理）

- CRYPTO1、金鑰流與弱點概念介紹: https://zhuanlan.zhihu.com/p/465900396
- Ciphertext-only cryptanalysis on hardened Mifare classic cards: https://pure.tue.nl/ws/files/46945242/855438-1.pdf
- Study of vulnerabilities in MIFARE Classic cards: https://www.sidechannel.blog/en/mifare-classic-2/

Mifare 卡與讀卡機的通訊協定示意:
![Mifare 通訊示意](https://hackmd.io/_uploads/HJTTjz2Hlg.png)

Mifare Classic M1 加密演算法 Crypto1:
![Crypto1 示意](https://hackmd.io/_uploads/Skn5sz3Hxg.png)

另一張示意圖：
![Crypto1 內部](https://hackmd.io/_uploads/B1q8Wl48ll.png)

### Darkside Attack（重點筆記）

- 論文: THE DARK SIDE OF SECURITY BY OBSCURITY and Cloning MiFare Classic Rail and Building Passes, Anywhere, Anytime: https://eprint.iacr.org/2009/137.pdf

核心要點：

- 當攻擊者能控制或預測 reader ↔ card 的部分回應（例如 parity bits），卡片可能會在特定情況下回傳 4-bit encrypted NACK (0x5)。這個已知的 NACK 值可被利用來洩漏 keystream（ks）。
- Crypto1 中的布林函數特性差，導致在解密某些位元時 keystream 對明文字位元的依賴性低（有些位元在 0.75 的機率下不依賴於某些輸入位元），因此可以用差分或預計算表格來還原內部狀態。
- 論文發現：在 card-only 情境下，對偽造密文有唯一一組 8 個位元會讓卡回應那個 4-bit 的 encrypted NACK，且該現象約以 1/256 的機率發生（不同卡廠會有差異）。
- 亂數（nonce）生成在某些情況可被時序控制或預測，進一步降低攻擊門檻。

### Nested Attack

- 參考: Wirelessly Pickpocketing a Mifare Classic Card: https://www.researchgate.net/publication/220713937_Wirelessly_Pickpocketing_a_Mifare_Classic_Card

原理重點：若已知一個 sector 的 key，攻擊者在與卡互動的過程中可藉由時間/nonce 的相關性快速推斷出其他 sector 的 key，使得在已知少量資訊時能快速擴大對整張卡的控制。

### Hardnested Attack

- 參考: Ciphertext-only cryptanalysis on hardened Mifare classic cards: https://pure.tue.nl/ws/files/46945242/855438-1.pdf

這類攻擊屬於 ciphertext-only 或加強版的差分分析，目標是對宣稱已加固（hardened）的卡仍能在不完整資料下還原 key 或內部狀態。

### 悠遊卡（EasyCard）重要欄位（摘自 Part 3: EasyCard - Reverse Engineering an RFID payment system）

下面的欄位表格整理了常見的 offset 與用途（dependent on 卡片與版本可能有差異，僅供參考）：

| offset        | 用途                        | 補充                    |
| ------------- | --------------------------- | ----------------------- |
| 0x0 ~ 0x3     | uid                         |                         |
| 0x4           | uid 各 byte 的 xor (BCC)    |                         |
| 0x5 ~ 0x8     | 發行日期 timestamp          |                         |
| 0x90 ~ 0x93   | 當前餘額                    |                         |
| 0x94 ~ 0x97   | 當前餘額 ^ 0xffffffff       |                         |
| 0xa1 ~ 0xa4   | 上次加值日期 timestamp      |                         |
| 0xa6 ~ 0xa7   | 上次加值金額                |                         |
| 0xab          | 加值的車站代號 ^ 0xff       |                         |
| 0xac ~ 0xaf   | 上次加值的 RFID 讀取機的 id |                         |
| 0x121 ~ 0x124 | 上次交易日期 timestamp      |                         |
| 0x126 ~ 0x127 | 上次交易金額                |                         |
| 0x128 ~ 0x129 | 上次交易前的餘額            |                         |
| 0x12b         | 上次交易類別                | 05 = 公車               |
| 0x12c ~ 0x12f | 上次交易的 RFID 讀取機 id   |                         |
| 0x1d4         | 最後離站的車站代號          | 車站代號有些卡會 ^ 0xff |
| 0x1d9 ~ 0x1dc | 最後離站日期 timestamp      |                         |
| 0x1e4         | 最後進站的車站代號          | 車站代號有些卡會 ^ 0xff |
| 0x1e9 ~ 0x1ec | 最後進站日期 timestamp      |                         |

我自己在 2025/07/11 對新買的 Mifare Classic EV1 做過測試，用 hardnested attack 仍能成功破解某些 sector 的 key，下面是我在那張卡上觀察到的 offset 與用途（實務上會依卡廠與版本不同）：

| offset        | 用途                     | 補充                                                                                                                           |
| ------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| 0x0 ~ 0x3     | uid                      |                                                                                                                                |
| 0x4           | uid 各 byte 的 xor (BCC) |                                                                                                                                |
| 0x80 ~ 0x83   | 當前餘額                 |                                                                                                                                |
| 0x84 ~ 0x87   | 當前餘額 ^ 0xffffffff    |                                                                                                                                |
| 0x88 ~ 0x8b   | 當前餘額                 |                                                                                                                                |
| 0x90 ~ 0x93   | 當前餘額                 |                                                                                                                                |
| 0x94 ~ 0x97   | 當前餘額 ^ 0xffffffff    |                                                                                                                                |
| 0x98 ~ 0x9b   | 當前餘額                 |                                                                                                                                |
| 0xa0          |                          | 奇岩站加值 100 元後從 00 變 02；奇岩站加值 10 元後從 02 變 03；復興崗站加值 14 元後從 03 變 04；奇岩站加值 100 元後從 04 變 07 |
| 0xa1 ~ 0xa4   | 上次加值日期 timestamp   |                                                                                                                                |
| 0xa5          |                          | 奇岩站加值 100 元後從 00 變 30                                                                                                 |
| 0xa6 ~ 0xa7   | 上次加值金額             |                                                                                                                                |
| 0xa8 ~ 0xa9   | 當前餘額                 |                                                                                                                                |
| 0xaa          |                          | 奇岩站加值 100 元後從 00 變 02                                                                                                 |
| 0xab          | 加值的車站代號           |                                                                                                                                |
| 0xac ~ 0xaf   |                          | 上次寫入的 RFID 讀取機的 id                                                                                                    |
| 0xc0          |                          | 奇岩站加值 10 元後從 01 變 03；全家消費 42 元後從 03 變 05；奇岩站加值 100 元後從 05 變 07                                     |
| 0xc2          |                          | 全家消費 42 元後從 05 變 00；奇岩站加值 100 元後從 00 變 01                                                                    |
| 0x100 ~ 0x10f |                          | 全家消費 42 元後從 00..00 變 05 D4 6B 79 68 20 2A 00 52 00 49 00 B3 D7 49 00                                                   |
| 0x110 ~ 0x11f |                          | seven 消費 65 元後從 00..00 變 06 EA BC 7A 68 20 41 00 11 00 4B 01 BB E2 4B 00                                                 |
| 0x181         |                          | 奇岩站加值 100 元後從 0c 變 0a                                                                                                 |
| 0x183 ~ 0x184 |                          | 奇岩站加值 100 元後從 04 44 變 02 22                                                                                           |
| 0x18d         |                          | 奇岩站加值 100 元後從 00 變 04；復興崗站加值 14 元後從 04 變 08；seven 消費 65 元後從 08 變 0c                                 |
| 0x18f         |                          | 奇岩站加值 100 元後從 4C 變 2E；復興崗站加值 14 元後從 2E 變 22；seven 消費 65 元後從 22 變 26                                 |
| 0x19d         |                          | 奇岩站加值 10 元後從 02 變 06；全家消費 42 元後從 06 變 0a；奇岩站加值 100 元後從 0a 變 0e                                     |
| 0x19f         |                          | 奇岩站加值 10 元後從 00 變 04；全家消費 42 元後從 04 變 08；奇岩站加值 100 元後從 08 變 0c                                     |
| 0x1a0         |                          | 奇岩站加值 100 元後從 00 變 02；復興崗站加值 14 元後從 02 變 04；seven 消費 65 元後從 04 變 06                                 |
| 0x1a2         |                          | seven 消費 65 元後從 05 變 01                                                                                                  |
| 0x3eb ~ 0x3ed |                          | 全家消費 42 元後從 00 00 00 變 f1 5a 2a；seven 消費 65 元後從 f1 5a 2a 變 f2 5a 41                                             |

### 其他卡種（簡要）

- 台北單程票: MIFARE Ultralight (MF0ICU1)，16 個 block，每 block 4 bytes
- 台中單程票: INFINEON my-dÖ move (SLE 66R01P)，38 個 block，每 block 4 bytes

## HITCON 活動組與教學資源

- HITCON 活動文件（內部教學 / 練習）：https://docs.google.com/document/d/1XFSWOimSZHIuBMYGdkqaA6YjcHJd4FRWh2AwFevkwuw/edit?usp=sharing

## 實作備忘（常用流程）

1. 讀 UID: `hf 14a read`
2. 嘗試自動爆破 sector key（若是老版 Mifare Classic 1）：`hf mf autopwn`
3. 取得 dump 並備份
4. 若要複寫到另一張可寫卡：`hf mf cload -f binary.dmp`
5. 若要恢復（需要 key file）: `hf mf restore -f <dump> -k <keyfile>`

以下是我平常會在教學或示範時示範的指令摘錄（同上，但以清單方式備份）：

```
hf search
hf mf info
hf mf rdbl --blk 0
hf mf wrbl --blk 0 -d <block0data> --force
hf mf csetuid -u <UID> --atqa <ATQA> --sak <SAK>
```

## 2025 HITCON NFC Hacking 活動

看完前面的介紹應該就能看懂 2025 HITCON NFC Hacking 活動播放的影片的意思了。

1. 介紹 Mifare Classic 1K 的資料結構：共 16 sector，每個 sector 包含 4 block，每個 block 包含 16 bytes，總共 1024 byte
2.

- Darkside attack 的原理（用圖說明 keystream 泄漏、encrypted NACK）
- Nested attack 的原理（如何利用已知 key 擴散）
- Hardnested / ciphertext-only 攻擊概念
- NXP 的新卡（DESFire）以及法規與實務上對複製、竄改有價證券的懲罰與管理（法律面簡介）

<video src="https://www.youtube.com/watch?v=LWHVHA7Ml4k" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>
