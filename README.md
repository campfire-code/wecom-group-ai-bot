# 企微群 AI 答疑机器人

> 篝火出品 · 收录于篝火 App 应用区 · 基于开源项目 [easy-wx/wecom-bot-svr](https://github.com/easy-wx/wecom-bot-svr)（MIT）

在企业微信群里 @机器人 提问，机器人先到你放好的 Markdown 知识库里检索，再调用大模型按资料作答；资料里没有就按固定话术回复，不乱编。

## 部署（Docker）

需要一台能被企业微信访问到的服务器（公网地址，建议配 HTTPS 反向代理），装好 Docker。到 [Releases](https://github.com/campfire-code/wecom-group-ai-bot/releases/latest) 下载 `docker-compose.yml` 和 `.env.example`：

```bash
mkdir wecom-group-ai-bot && cd wecom-group-ai-bot
# 放入 docker-compose.yml，把 .env.example 改名为 .env 并填写
mkdir kb        # 把知识库 .md 文件放进来
docker compose up -d
curl http://127.0.0.1:5001/healthz     # 返回 ok 即启动成功
```

镜像：`ghcr.io/campfire-code/wecom-group-ai-bot:latest`（x86 / ARM）。

## 需要准备的配置

**1. 企业微信群机器人的「接收消息配置」**（在群里添加群机器人，机器人资料页里设置，步骤与截图见下方上游原文第 2.3、3 节）：

| 企业微信里的字段 | 填到哪里 |
|---|---|
| 回调地址 | `https://你的域名/wecom_bot`（路径可用 `CALLBACK_PATH` 改） |
| Token | `.env` 的 `WX_BOT_TOKEN` |
| EncodingAESKey | `.env` 的 `WX_BOT_AES_KEY` |
| 机器人名称 | `.env` 的 `WX_BOT_NAME`，必须与群里 @ 的名字一致（用于去掉消息里的 @名字） |
| Webhook 地址中 `key=` 后面的值 | `.env` 的 `WX_BOT_KEY`（可选，见下） |

保存回调配置时企业微信会请求回调地址做校验，服务正常运行才能保存成功。

**2. 大模型**（兼容 OpenAI 接口格式，由你自己提供）：`LLM_BASE_URL`（填到 `/v1` 为止，程序会请求 `<地址>/chat/completions`）、`LLM_API_KEY`、`LLM_MODEL`。密钥只存在你的 `.env`，不会写入日志。

可选项：`KB_FALLBACK_REPLY`（知识库没有时的话术，默认“抱歉，知识库里暂时没有这个问题的答案……”）、`KB_TOP_K`（取几段资料，默认 4）、`MAX_REPLY_CHARS`（回复最长字数，默认 1500，是本工具自己的限制）。

关于 `WX_BOT_KEY`：上游框架同步回包最多等约 4 秒，超时后改为通过 Webhook 主动推送，推送要用这个 key。大模型响应慢时必须配置，否则用户收不到答案（启动日志会提醒）。

## 知识库怎么放

- 把 `.md` / `.markdown` 文件放进挂载目录（默认 `./kb` → 容器内 `/data/kb`），支持子文件夹，UTF-8 编码；增删改文件无需重启，下一次提问自动生效。
- 程序按标题和空行把文件切成约 600 字的段落，用关键词（英文单词、中文两字词）匹配，取得分最高的几段交给大模型。所以**标题写清楚、一个段落讲一件事**，检索效果最好。仓库里的 `kb-example/` 是示例。
- 检索是纯关键词匹配，不做同义词理解（例如问“到账”，资料里只写“退回”可能搜不到）。常见问法最好直接写进资料。
- 检索不到任何相关段落时不会调用大模型，直接回复固定话术；大模型判断资料不足时同样回复固定话术。

## 验收用例

用仓库里的 `kb-example/` 作知识库启动后：

| 操作 | 应得到 |
|---|---|
| 浏览器或 `curl` 访问 `http://服务器:5001/healthz` | 返回 `ok` |
| 在企业微信机器人配置页保存回调地址 | 保存成功 |
| 群里发：`@答疑助手 退款流程是什么` | 机器人依据《退款政策》回答审核时间与到账时间 |
| 群里发：`@答疑助手 你们老板叫什么名字` | 回复“知识库里暂时没有这个问题的答案”类话术 |
| 群里发图片或文件给机器人 | 回复“目前只支持文字提问” |
| 查看 `docker logs` | 没有 token、AESKey、API key、Webhook key 的明文（出现处显示 `***`） |

开发者自测：`pip install -r requirements-campfire.txt pytest && python -m pytest tests`（用假大模型和手工构造的回调样例，不联网，含加解密往返）。

## 和上游的区别

- 上游只是回调框架（加解密、URL 校验、收发消息），自带 demo 不接大模型。本工具在 `campfire_bot/` 新增：知识库检索、提示词组装、OpenAI 兼容调用、日志脱敏，以及 Docker 部署文件；`src/` 下框架代码未改动。
- 篝火新增代码同样使用 MIT 许可证。
- 日志脱敏：把 Token、AESKey、API key 的值以及 `key=…` 参数替换为 `***`。上游框架会把解密后的群消息原文写进 info 日志（含提问内容），日志里可能有群聊内容，请勿公开。

## 已知限制

- 上游使用 Flask 自带服务器，适合小团队群机器人，不适合高并发。
- 只处理文字（及图文混排里的文字）；不记忆上下文，每次提问独立回答。
- 企业微信回调消息的具体字段以上游 `src/wecom_bot_svr/req_msg.py` 为准，回调加密协议细节以企业微信官方文档（上游 README 引用的回调功能说明）为准；本工具未单独核对其他字段。
- 上游遇到未知消息类型时可能抛异常（`ReqMsg.create_msg` 返回 None），未修改。

## 归属与许可证

- 上游：[easy-wx/wecom-bot-svr](https://github.com/easy-wx/wecom-bot-svr)，作者 Pan Zhongxian，MIT，`LICENSE` 保留原文。
- 篝火新增部分：MIT。

---

# 以下为上游原文 README

# 企业微信机器人回调服务

如果项目能给你带来些许便利，请不吝 Star

- 2024-12-09 新增发送主动文件功能(可以由消息触发)
- 2025-02-08 新增主动发送消息服务(本地网络POST触发)
- 2026-03-24 **默认支持高延迟回复消息，支持生成器多条消息回复**(生成器形式，受限于限频，4条内比较保险)

![delay_and_multiple_msg](https://github.com/easy-wx/wecom-bot-svr/raw/main/images/delay_and_multiple_msg.png)

## 1. 介绍

本项目是一个基于 [Flask](https://flask.palletsprojects.com/en/1.1.x/)的**企业微信机器人回调功能的接口服务简单框架**
。使用者只需要实现两个简单的函数，即可快速搭建一个企业微信机器人回调功能的接口服务。

实现过程参考企业微信机器人[回调功能说明文档](https://developer.work.weixin.qq.com/document/path/99399)
，以及相关文档中指引使用的[加解密脚本](https://github.com/sbzhu/weworkapi_python/tree/master/callback)。

## 2. 使用

这里提供一个 [demo.py](./demo/demo.py)，只要安装好依赖，修改好配置，即可直接进行部署服务。

### 2.1 本地调试

需要安装依赖，然后拉起 demo.py 即可(*这里暂时使用固定的 token 和 AESKey，后续在实际配置时可以替换掉*)：

```bash
pip3 install wecom-bot-svr
python3 demo.py
```

拉起服务后，可以使用 curl 进行测试(下边的测试链接对应demo中原始的 token 和 AESKey)：

```bash
curl 'http://127.0.0.1:5001/wecom_bot?msg_signature=09380007d4f0891d966988e5450ad794c77fa01c&timestamp=1703041184&nonce=1703023880&echostr=oCdlC8pJ%2FDIjXnC8F9reyjDYlSImCmIgxA4prPD%2Bl2Fj5qBHjFiWnpelQofsDCJrSEvNVTET6oQmoXLQxzUkyQ%3D%3D'
```

### 2.2 Docker方式部署

如果你计划单独的去部署这个机器人回调服务，可以直接使用我这里提供的Docker方式。

```bash
cd demo
docker build -t wx_bot docker.io/panzhongxian/wecom-bot-svr-demo:latest .
docker push docker.io/panzhongxian/wecom-bot-svr-demo:latest
```

然后在对应的平台中选择镜像部署，配置好对应的域名，即可获得在后续步骤中需要的回调地址。

如果你需要跟别的服务部署在一起，或者直接在CVM的机器上启动，在运行之前，记得安装 `wecom-bot-svr` 即可

### 2.3 配置企业微信群机器人

找一个群，在右上角点击「...」，点击「添加群机器人」，点击「接收消息配置」， 这里对应 demo 我们填入回调地址、token、AESKey。

<img src="https://github.com/easy-wx/wecom-bot-svr/raw/main/images/new_wecom_bot.png" alt="new_wecom_bot" style="zoom:33%;" />

如果服务正常，这里将会保存成功；如果服务异常，这里会提示失败。

### 2.4 测试

在添加到群中之后，可以在群中发送消息。demo里有**实现 help 和普通消息的回复**功能:

<img src="https://github.com/easy-wx/wecom-bot-svr/raw/main/images/add_wecom_bot.png" alt="add_wecom_bot" style="zoom:50%;" />

也可以移除再添加，这里展示的是**加入群的事件触发消息发送**的功能:

<img src="https://github.com/easy-wx/wecom-bot-svr/raw/main/images/wecom_bot_join.png" alt="wecom_bot_join" style="zoom:50%;" />

### 2.5 发布到公司

查看机器人资料，有一个发布到公司的按钮，只有发布之后的机器人，才能被公司其他同事搜索到，才可以被添加到其他的群聊当中：

<img src="https://github.com/easy-wx/wecom-bot-svr/raw/main/images/publish_wecom_bot.png" alt="publish_wecom_bot" style="zoom:50%;" />

## 3. Token和AESKey的管理

为了方便，demo中直接使用固定的 Token 和 AESKey，实际使用中，建议直接利用机器人配置页面的**随机生成**按钮获得。

<img src="https://github.com/easy-wx/wecom-bot-svr/raw/main/images/random_token_1.png" alt="random_token_1" style="zoom:50%;" />

删除代码中传入的 token 和 key，直接将其以配置的方式传入到服务中即可(
三个环境变量 `WX_BOT_TOKEN`, `WX_BOT_AES_KEY`, `WX_BOT_CORP_ID`):

```python
server = app.WecomBotServer(bot_name, host, port, path='/wecom_bot')
```

<img src="https://github.com/easy-wx/wecom-bot-svr/raw/main/images/random_token_2.png" alt="random_token_2" style="zoom:50%;" />

## 4. demo.py 代码解析

只要你看懂了 demo.py 里边做了什么工作，就可以修改他，实现自己机器人的回复逻辑了。

- `msg_handler`: 消息处理函数。除 help 与默认回显外，演示了**高延迟单条回复**、**生成器多条回复**、**多类型主动消息**等用法（见下）
- `event_handler`: 事件处理函数，简单的实现了加入群聊的事件触发消息发送的功能
- `WecomBotServer`: 企业微信机器人回调服务的接口服务，实现了加解密的功能，运行后能拉起 HTTP 服务
- 通过`set_message_handler`和`set_event_handler`将消息处理函数和事件处理函数注册到服务中

### demo 中文本指令（群聊 @ 机器人后发送）

- `help`：Markdown 帮助（含下列指令说明）
- `sleep N`：在 handler 内休眠 N 秒再回复一条文本（演示超过同步回包等待时间时的超时与主动推送行为，具体以 `WecomBotServer` 实现为准）
- `repeat N`：返回**生成器**，连续推送 N 条文本（`msg 1/N` … `msg N/N`）
- `full_media_test`：返回**生成器**，依次推送 **text → markdown → file → news**：其中文件写入当前目录下的 `full_media_test_4-3.txt`，内容与 `give me a file` 示例文案一致；各步之间有短暂 `sleep`，便于观察顺序
- `give me a file`：写 `output.txt` 并调用 `server.send_file` 发文件，同步回包为空的 `RspTextMsg()`（与生成器路径对照时，注意主动推送条数对企业微信频控的影响）

### 消息格式说明

`msg_handler(req_msg, server) -> rsp_msg | Generator`：第二个参数为 `WecomBotServer` 实例，便于在 handler 内调用 `send_file` 等能力；返回值可以是**单个**响应消息对象，也可以是 **generator**，逐条 `yield` 多个 `Rsp*`；生成器时**第一条**通常作为同步加密回包，**后续条**由框架通过 webhook 主动发送（详见库内 `_dispatch_message_handler_with_timeout` / `_handle_message_handler_generator`）。

所有机器人接收到的消息和事件，罗列在 req_msg.py 中，会作为 msg_handler 的输入，已经提取到具体的格式，用户可以根据自己的需求使用。

机器人侧响应类型定义在 rsp_msg.py 中，除 Text、Markdown 外，还包括 **File**（`file_path` / `media_id`）、**Image**（`base64_image_data` + `md5`）、**News**（标题、描述、链接、配图 URL 等）。demo 中 `full_media_test` 覆盖了 text、markdown、file、news；需要图片类型时可参考文件中预留的 1×1 PNG 常量扩展。

## 5. 发送文件

![send_file](https://github.com/easy-wx/wecom-bot-svr/raw/main/images/send_file.png)

原理链接：<https://developer.work.weixin.qq.com/document/path/91770#%E6%96%87%E4%BB%B6%E7%B1%BB%E5%9E%8B>

将上述上传文件、发送文件进行了封装，作为 WecomBotServer 的一个方法，可以被调用。

可以在消息处理函数中，通过调用 `send_file(chat_id, file_path)` 方法，将文件发送到群聊中。

当然，你也可以通过其他方式，调用该函数主动发送。

这里需要在构造函数中，增加传入 `bot_key`，用于发送文件的权限校验。这个key是在 WebHook 的链接中可以查询到：

![webhook_key.png](images%2Fwebhook_key.png)

同时，你需要加在消息处理函数的参数中，增加 `server` 参数，用于调用发送文件的方法。

```python
def msg_handler(req_msg: ReqMsg, server: WecomBotServer):
    ...
    # 生成文件、发送文件可以新启线程异步处理
    with open('output.txt', 'w') as f:
        f.write("This is a test file. Welcome to star easy-wx/wecom-bot-svr!")
    server.send_file(req_msg.chat_id, 'output.txt')
    return RspTextMsg()  # 不发送消息，只回复文件
```

## 6. 主动触发消息发送

单独启动了一个路由（默认为 ``/active_send``），用于接收主动发送消息的触发。

这样做的好处是**可以隔离机器人消息管理和其他需要发送消息的应用**，解耦**消息发送逻辑**和**消息内容组织与触发的逻辑**。

考虑到安全性，该路由只处理本地网络的 POST 请求，外网请求会直接返回错误。默认的路由，可以通过路径来指定。

```python
import requests

url = "http://127.0.0.1:5001/active_send"
data = {"msg_type": "text", "chat_id": "12345", "content": "主动消息推送测试"}

response = requests.post(url, data=data)

print(response.text)
```

以上代码中 `chat_id`，如果给个人发送则是其ID，如果是群发，则是群的ID。

![active_send](https://github.com/easy-wx/wecom-bot-svr/raw/main/images/active_send.png)

![active_send](https://github.com/easy-wx/wecom-bot-svr/raw/main/images/active_send_group.png)

## 7. TODO

- 增加默认权限支持


## 8. Star History

[![Star History Chart](https://api.star-history.com/svg?repos=easy-wx/wecom-bot-svr&type=Date)](https://star-history.com/#easy-wx/wecom-bot-svr&Date)