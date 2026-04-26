---
layout: post
title:  "如何使用 NamedPipeMaster"
date:   2026-04-28
translation_group: how-to-use-NamedPipeMaster
---

C 學是混學的基礎，C 是為了讓之後更好的混。做好工具再研究相關的主題都會輕鬆很多。

[NamedPipeMaster](https://github.com/zeze-zeze/NamedPipeMaster) 是我在 2024 寫的一個小工具，可以動態觀察 named pipe 之間的溝通。

### 使用環境
到 [release](https://github.com/zeze-zeze/NamedPipeMaster/releases) 頁面根據作業系統下載 zip 檔案，裡面有 Ring3NamedPipeConsumer.exe、Ring3NamedPipeMonitor.dll、Ring0NamedPipeFilter.sys。

由於 Ring0NamedPipeFilter.sys 沒有簽章，連測試簽章都沒有，所以直接載入系統會失敗。

我通常都在虛擬機安裝 [VirtualKD-Redux](https://github.com/4d61726b/VirtualKD-Redux)，重新開機後在開啟選項中選擇 F8 => 停用驅動程式強制簽章。

如果 driver 載入失敗，在執行 Ring3NamedPipeConsumer.exe 時會輸出 `[warning] LoadDriver error. Start without Ring0NamedPipeFilter`。


### 使用方式
把 Ring3NamedPipeConsumer.exe、Ring3NamedPipeMonitor.dll、Ring0NamedPipeFilter.sys 放到同個目錄，然後用 Administrator 權限開啟 cmd，cd 到放檔案的目錄後執行 Ring3NamedPipeConsumer.exe。

執行之後會跳出選單
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
輸出錄到的 named pipe event，目前支援五種 event：
- CMD_CREATE_NAMED_PIPE: named pipe server 建立 named pipe
- CMD_CONNECT_NAMED_PIPE: named pipe server 等待 named pipe client 連接
- CMD_CREATE: named pipe client 連接 named pipe
- CMD_READ: 從 named pipe 讀取資料 
- CMD_WRITE: 往 named pipe 寫入資料

#### [2] start monitor mode
即時輸出錄到的 named pipe event

#### [3] clear database
把錄到的 named pipe event 清空

#### [4] get database info
統計目前錄到的 named pipe event 資訊
- 監控總時長
- 幾筆 named pipe event
- 從哪個程式錄到哪些 named pipe

#### [5] filter
NamedPipeMaster 可以篩選自己有興趣的 named pipe event。
```
[a] Filter cmdId: all (0=all, 1=CMD_CREATE_NAMED_PIPE, 2=CMD_CREATE, 3=CMD_READ, 4=CMD_WRITE, 5=CMD_CONNECT_NAMED_PIPE)
[b] Filter sourceType: all (0=all, 1=SOURCE_MINIFILTER, 2=SOURCE_INJECTED_DLL)
[c] Filter processId: all (0=all)
[d] Filter imagePath: %%
[e] Filter fileName: %%
[f] Filter canImpersonate: all (0=all, 1=yes)
[g] Reset filter
```

- [a] Filter cmdId: 只錄選擇的 named pipe event
- [b] Filter sourceType: 選擇錄 named pipe event 的來源，目前有從 driver 和從 dll 兩個來源。driver 的只要有載入成功就能收到整個系統的 named pipe event，dll 則要用 [6] inject dll 功能注入目標 process 後才會收到目標 process 產生的 named pipe event。選擇 SOURCE_MINIFILTER 只接收 driver 來的，選擇 SOURCE_INJECTED_DLL 只接收目標 process 的。
- [c] Filter processId: 選擇只接收目標 pid 的 named pipe event
- [d] Filter imagePath: 選擇只接收包含目標 process image path 子字串的 named pipe event
- [e] Filter fileName: 選擇只接收包含目標 named pipe 名稱子字串的 event
- [f] Filter canImpersonate: 只有在偵測到可以 impersonate 的狀況下才錄 named pipe event
- [g] Reset filter: 重置 filter


#### [6] inject dll
注入 Ring3NamedPipeMonitor.dll 進目標 pid，相比 Ring0NamedPipeFilter.sys，它多了功能：
- 在 named pipe server 接收到 named pipe client 的連線時，確認 named pipe client 能否 impersonate
- 在收到 named pipe event 時會把 call stack 印出來，幫助在逆向分析時快速定位觸發 named pipe event 的程式碼


#### [7] NamedPipePoker
把自己當作 named pipe client 主動連接 named pipe server，輸入的 pipe name 格式如 `\\.\pipe\<pipename>`

如果成功連接上 named pipe server，接著會跳出讀寫 named pipe 的介面
```
NPM-CLI> 7
pipe name: \\.\pipe\<pipename>

    [a] Write data (alive: yes)
    [b] Read data (total 0 data)
    [c] Test impersonation
    [d] exit

    choice:
```

- [a] Write data: 輸入想傳給 named pipe server 的資料
- [b] Read data: 接收 named pipe server 傳來的資料
- [c] Test impersonation: 這只適用 [9] NamedPipePoked
- [d] exit: 離開互動介面

這個功能可以快速觸發目標 named pipe server 的 named pipe event，讓 NamedPipeMaster 可以錄到 named pipe server 產生的 named pipe event。

#### [8] NamedPipeProxyPoker
注入 Ring3NamedPipeMonitor.dll 到目標 pid，把目標 process 當作 named pipe client 連接到目標 named pipe server。

```
NPM-CLI> 8
target pid: <pid>
target pipe name: \\.\pipe\<pipe name>
Inject pid <pid> successfully.

    [a] Write data (alive: yes)
    [b] Read data (total 0 data)
    [c] Test impersonation
    [d] exit

    choice:
```

互動方式跟 [7] NamedPipePoker 相同，差別只在於 named pipe server 會認為發起 named pipe event 的是你注入的目標 process。

這個功能在面對會檢查 named pipe client 的簽章或 image path 的 named pipe server 時可以很方便的繞過檢查。


#### [9] NamedPipePoked
把自己當作 named pipe server，等待 named pipe client 連上來。
```
NPM-CLI> 9
pipe name: \\.\pipe\<pipe name>

    [a] Write data (alive: no)
    [b] Read data (total 0 data)
    [c] Test impersonation
    [d] exit

    choice:
```

互動方式跟 [7] NamedPipePoker 相同，差別只在於 [c] Test impersonation 可以確認 named pipe client 能不能 impersonate。

這個功能在知道如何觸發 named pipe client 的狀況下，假冒自己是 named pipe client 的目標 named pipe server 時很方便。


#### [10] help
顯示 help 選單

#### [11] exit and clean up
離開 NamedPipeMaster，會把 driver 卸載，但是已經注入 Ring3NamedPipeMonitor.dll 的 process 不會重啟。