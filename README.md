# session-bridge

A Claude Code mod that lets you talk to your open Claude Code sessions from somewhere else: from another session, from your voice, or from any program on the same PC. Two sessions can also hold a meeting with you.

The commands and messages are in Japanese. Tested on Windows 11 with Claude Code 2.1.286 to 2.1.288 (the version with function-hook plugins, "mods").

## What it does

| Command | What happens |
|---|---|
| `/namae ぽーたる` | Gives this session a name, so others can call it |
| `/tell ぽーたる 今どこまで進んだ？` | Sends a message to the session named ぽーたる. Its answer pops up here |
| `/sessions` | A pane with the running sessions and recent exchanges |
| `/kaigi ぽーたる` | Starts a meeting with ぽーたる. Whatever you say in either session goes to both, and the two Claudes reply to each other up to 3 round trips. `/kaigi おわり` ends it |
| `/kaiwa` or the 🔊 button | Talk mode: replies are read aloud, then it listens and sends what you say. Needs a voice listener (see below) |

From a program on the same PC:

```bash
python bridge.py list
python bridge.py send ぽーたる "テストは通った？" --from 声 --wait 300
```

`bridge.py` finds a session by its `/namae` name or by its title in the app (part of the title is enough, and common English words such as GitHub also match their katakana reading). If two sessions match equally, it asks which one.

## Install

In Claude Code:

```
/plugin marketplace add tsurutanmen/session-bridge
/plugin install session-bridge@session-bridge
```

Sessions without a screen (`claude -p`, scheduled runs) get no inbox, so automated jobs are never interrupted.

## What it does on your PC

- **Reads and writes** JSON files under `~/.claude/session-dash/` only (the layout is below). Nothing else on disk.
- **Runs nothing.** The mod starts no processes. `bridge.py` is a separate script you run yourself.
- **Opens no network connection** and listens on no port. Messages travel as files on this PC.
- **Submits prompts** into the session it runs in, but only for messages found in that session's inbox, framed as 「〇〇からの伝言」.
- **Refuses tools** while it answers a read-only message: everything except Read, Glob, Grep, LS, ToolSearch and TodoWrite.

## Safety: read this first

- A message is put into the session as 「〇〇からの伝言」 (a message from someone). It never pretends to be you, except in talk mode, where the words are yours.
- Messages from programs (`bridge.py`, a voice assistant) are **read-only by default**. While the session answers one, the mod refuses every tool except Read, Glob, Grep, LS, ToolSearch and TodoWrite. This is a hook that blocks tool calls inside that session. **It is not full isolation.** The session can still read anything its own permissions let it read.
- `/tell` from a session, `bridge.py send --do`, talk mode and meetings are **not read-only**. The other session can edit files and run commands with its own permissions. Meetings tell both sides to announce a file before touching it and to ask you before anything that leaves the PC or deletes data, but that is a request, not a guard.
- Any program on your PC that can write to `~/.claude/session-dash/bridge/` can send messages. Don't install it on a machine you share.

## How it works

Everything is plain JSON files under `~/.claude/session-dash/`:

```
bridge/sessions/<id>.json        each session's card (name, folder, last prompt, busy), written every 3 s
bridge/inbox/<id>/<msgid>.json   messages to a session { id, from, text, mode: ask|do, kind? }
bridge/outbox/<msgid>.json       the answer { id, session, answer, isAborted }
bridge/meetings/<id>.json        a meeting (two sessions and you)
bridge/config.json               { "owner": "your name" } — how meetings call you (default 持ち主)
speak/<time>.json                replies to read aloud { text, voice?, session?, listen? }
wake.alive                       touched every 10 s by a voice listener, if you run one
```

The mod polls its inbox every 3 seconds. When the session is idle it submits the oldest message with `$.prompt.submit`, and writes the turn's answer to the outbox on `turn.complete`.

### Voice listener (optional)

Talk mode and meeting voices need a separate program that reads `speak/*.json` aloud and touches `wake.alive`. If an item has `"listen": true`, it should beep, record what you say, and send it back with:

```python
import bridge
bridge.post({"id": item["session"]}, heard_text, frm="声（本人）", mode="do", kind="voice")
```

The author's listener uses Vosk for recognition and VOICEVOX for speech. It isn't published yet.

## Related

Five tools that work together, all MIT:

| | |
|---|---|
| [homedot](https://github.com/tsurutanmen/homedot) | A Dots-style personal agent on Claude Code, in a WSL2 VM on your own PC |
| [session-bridge](https://github.com/tsurutanmen/session-bridge) | Let open Claude Code sessions talk to each other, hold meetings, and answer your voice |
| [claude-desk](https://github.com/tsurutanmen/claude-desk) | "Hey Claude" voice listener with VOICEVOX replies, and a desktop wallpaper of your sessions |
| [homedot-panel](https://github.com/tsurutanmen/homedot-panel) | homedot and the 5-hour limit in Claude Code's status line |
| [session-dash](https://github.com/tsurutanmen/session-dash) | Usage limits above the prompt, and every open session in one pane |

More Claude Code plugins: [tsurutanmen/claude-plugins](https://github.com/tsurutanmen/claude-plugins)

## License

MIT

---

## 日本語

開いている Claude Code のセッションに、ほかのセッション・声・同じPCのプログラムから話しかけるための mod。2つのセッションと自分の3人で会議もできる。

- `/namae 名前`：このセッションに名前を付ける
- `/tell 名前 伝言`：ほかのセッションに伝言する。返事はお知らせで届く
- `/sessions`：動いているセッションと、最近のやりとり
- `/kaigi 名前`：会議を始める。自分が話すと両方のClaudeに回り、Claude同士が最大3往復する。`/kaigi おわり` で終わる
- `/kaiwa`・🔊：会話モード。返事を読み上げて、読み終えたら声を聞いてそのまま送る。声の聞き役が別に要る

外のプログラムからの伝言は、既定で「読むだけ」。読む道具のほかは mod が止める。ただし、そのセッションの中で道具を止める仕組みで、完全な隔離ではない。`/tell`・会議・会話モードは作業もできる。
