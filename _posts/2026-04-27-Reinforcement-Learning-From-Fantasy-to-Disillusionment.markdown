---
layout: post
title:  "強化學習 - 從幻想到幻滅"
date:   2026-04-27
translation_group: Reinforcement-Learning-From-Fantasy-to-Disillusionment
---

作為一個成熟的混子，我們要嘗試學習各面向的知識，雖然不一定能學會。但要是學會了，會的越多，能認的大哥就越多。

之前常常看到 youtube 上一些訓練 AI 玩遊戲的影片，我就一直想試試。剛好之前出題目拿 [tuanngokien/Crazy-Arcade](https://github.com/tuanngokien/Crazy-Arcade) 來改，所以對這單機遊戲算是熟悉。

### 入門教學
[Stable-Baseline3 Example](https://stable-baselines3.readthedocs.io/en/master/guide/examples.html) 中提供很多簡單的範例，拿 pygame 當作目標學習訓練 AI 玩遊戲。

其中一個範例是 LunarLander，遊戲按左右來控制太空船的平衡。

![image](/assets/Reinforcement-Learning-From-Fantasy-to-Disillusionment/LunarLander.gif)

範例程式碼也非常簡單，遊戲環境跟模型的演算法都包好了。

```
import gymnasium as gym
from stable_baselines3 import DQN
from stable_baselines3.common.evaluation import evaluate_policy

env = gym.make("LunarLander-v3", render_mode="rgb_array") # 遊戲環境，裡面幫我們處理好 agent 跟遊戲的溝通

model = DQN("MlpPolicy", env, verbose=1) # 模型使用 DQN 演算法
model.learn(total_timesteps=int(2e5), progress_bar=True)
model.save("dqn_lunar")

del model

model = DQN.load("dqn_lunar", env=env)
mean_reward, std_reward = evaluate_policy(model, model.get_env(), n_eval_episodes=10)
vec_env = model.get_env()
obs = vec_env.reset()
for i in range(1000):
    action, _states = model.predict(obs, deterministic=True) # 每個 step 要讓模型產生下一個動作 action
    obs, rewards, dones, info = vec_env.step(action) # 執行動作
    vec_env.render("human")
```

對於混子而言，模型的演算法改不動也不會改，只要根據遊戲性質挑選合適的演算法。

以這個範例而言，因為 gymnasium 套件把 agent 和遊戲環境之間的溝通都包好了，所以才可以方便的使用。但是對於新的遊戲，我們則要自己把它包成 gymnasium 的形式。

<br>
### 目標遊戲
這是類似爆爆王的遊戲，遊戲目標是要解鎖之後走到最右下角的門鎖通關。

首先要定義角色的 action，上、下、左、右、放炸彈。

![image](/assets/Reinforcement-Learning-From-Fantasy-to-Disillusionment/crazyarcade.png)

<br>
### 建立 Gymnasium 環境
參考 [Create a Custom Environment](https://gymnasium.farama.org/introduction/create_custom_env/) 把遊戲註冊成 gymnasium 的一個環境，與 stable-baseline3 接起來。

agent 會需要以下要素：
```
__init__(self, ...)
    self.observation_space = spaces.Box(...)：讓模型學習的遊戲狀態
    self.action_space = spaces.Discrete(...)：agent 給 env 的遊戲操作

step(self, action)：agent 與 env 的一步互動，輸入遊戲操作
    回傳 observation, reward, terminated, truncated, info

reset(self, *, seed=None, options=None)：初始化新的遊戲和狀態
```

原本遊戲邏輯可能如下：
```
while alive:
    move_character()
    move_bot()
    render_character()
    render_bot()
    render_map()
    # ......
```

現在就是要寫 agent 跟這個遊戲溝通，所以不管今天用的是什麼方法，http、socket、named pipe、rpc 都行，只要可以把資料從 agent 傳進遊戲和把資料從遊戲傳出來就好。

理想上 agent 跟遊戲接起來後的邏輯大概是這樣：
```
while alive:
    recv_agent_action()

    # game logic

    send_agent_obs()
```

因為我對 named pipe 比較熟悉，所以拿 named pipe 當 agent 和遊戲之間的溝通管道。
agent 擔任 named pipe client，遊戲則是 named pipe server。

![image](/assets/Reinforcement-Learning-From-Fantasy-to-Disillusionment/agent.png)


容易踩的坑：
- terminated vs truncated：模型對於這兩個事件的處理方式不同，所以誤用的話會導致模型學不起來
    - terminated 是遊戲終止 e.g. 死掉、超時
    - truncated 是強制遊戲的一個 episode 中斷的限制步數，超過會 reset
- 一個 action 配一個 observation：模型會根據當前的 action 和 observation 決定學習結果，如果 action 因為某個原因拿到不正確的 step 的 observation，模型就會學壞

<br>
### 開始訓練
#### 最初的嘗試
一開始我想得很單純，直接把整張地圖的資訊、取得的道具個數、玩家位置、敵人位置給模型，reward 也很簡單的只要角色不死就好，但又擔心太久都沒通關，所以每個 step 都扣 0.1。
```
if obs["player_dead"][0] == 0:
    reward += 0.1
else:
    reward -= 100.0
```

結果很快就被制裁了，模型覺得不管怎樣都會被扣分，一秒又好幾百個 step，所以乾脆一開場就把自己炸死了。


#### 認真的嘗試
這次稍微認真思考怎麼設定 observation 和 reward，因為上一個嘗試一直自殺，所以現在改成給它存活獎勵，產生遊戲進度再給其他獎勵。

- observation:
    - 整張地圖資訊
    - 角色狀態 (炸彈個數、速度、火力、盾牌)
    - 玩家、Bot 位置
- reward:
    - 存活獎勵：+0.1
    - 死亡懲罰：-100
    - 移動獎勵：+speed * 0.01
    - 獲得好道具：+2
    - 炸箱子：+5

角色這次終於不會自殺了，但是也都不動，靜靜的賺存活獎勵。後來才知道因為在訓練的過程中為了讓模型嘗試不同的路線，所以會有一定的隨機性，當角色選擇放炸彈後，又需要連續好幾個 step 都一直逃離炸彈，不然就會被炸死。導致模型學不會逃離炸彈，但放了炸彈又會死，所以乾脆都不動。


#### 拼命的嘗試
這次為了讓角色學會逃離炸彈，所以給了遠離炸彈獎勵。

- observation:
    - 整張地圖資訊
    - 角色狀態 (炸彈個數、速度、火力、盾牌)
    - 玩家、Bot 位置
    - 玩家是否處於危險 (爆炸範圍內)
    - 炸彈離爆炸的剩餘時間
- reward:
    - 存活懲罰：-0.01
    - 死亡懲罰：-500
    - 遠離炸彈獎勵：+speed * 0.01
    - 獲得好道具：+50
    - 炸箱子：+50

角色這次學會在放炸彈後，一直往同個地方遠離炸彈。但這又讓模型以為一直往同個地方走分數就會增加，然後就逃不離第二個炸彈了。


### 卡關 - 補理論知識
我使用的演算法是 Proximal Policy Optimization (PPO)，PPO 是 policy-based 演算法，PPO 用「限制每次策略更新幅度」的方式，讓 policy gradient 訓練變得穩定又好用。PPO 訓練步驟：
1. 取樣（Sampling）：使用舊策略跟遊戲互動
2. 計算優勢函數（Advantage）：計算每一個時間步的優勢函數值
3. 建立目標函數：建立 PPO 的目標函數
4. 最佳化策略：使用梯度下降等最佳化方法，最大化 PPO 的目標函數，得到新的策略參數
5. 反覆迭代：將更新後的策略視為新的舊策略，重複以上步驟

Policy Gradient:
![image](/assets/Reinforcement-Learning-From-Fantasy-to-Disillusionment/policy_gradient.png)

從原理中我們學到
- 取樣（Sampling），為了增加探索機會，會有一定的隨機性選擇下一個 action
    - reward 機制再複雜，模型走不到都沒用
- 越久以後的 reward 會因為折扣率 γ 而影響越小
    - 模型的 action 和對應的 reward 不能離太遠，放炸彈的 action 和箱子被炸掉的 reward 離太遠
- 限制每次策略更新幅度，偶然賽對一次，也不要期待模型直接學會
    - 就算某次賽到好結果，如果很難賽的話，也不一定學得到。目前遊戲的要素過多，會學得很慢。


### 學以致用
#### 調整遊戲環境
把遊戲環境變單純，並且角色的操作不那麼頻繁、讓 step 減少
- 改成 4x4 地圖
- 沒有道具
- 沒有 bot
- 角色每 30 ticks 只能做一個 action
- 角色每次移動就移動一格

#### 調整 Observation
減少模型的特徵維度，改成給以角色為中心點的資訊
- 以角色位置為中心點的附近地圖資訊
- 以角色位置為中心點的附近炸彈剩餘秒數
- 以角色位置為中心點的附近是否危險
    - 在炸彈範圍內
    - bot 的上下左右一格
- 門是否開啟

#### 調整 Reward
因為遊戲環境變單純，reward 機制也相對簡單。
目標變成只要炸開箱子找到鎖，解鎖後就可以走到右下角通關了
- 死亡時 -(炸掉的箱子數 * 50) - 20
- 抵達終點 +500
- 從危險中逃離 +4，除了放炸彈外進入危險 -4
- 在炸彈 countdown 很小且角色在炸彈範圍內 -20
- 把鎖開啟 +50
- 把炸彈放在能炸到箱子的地方 +50

#### Demo
<video src="/assets/Reinforcement-Learning-From-Fantasy-to-Disillusionment/5x5.mp4" style="max-width: 100%; width: 560px; height: auto; display: block;" controls preload="metadata" playsinline></video>