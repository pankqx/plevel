# Continue (VS Code) with local Ollama, fully offline

Plevel is for chatting. Continue puts the same local models inside VS Code: autocomplete as you type, chat with your code, edit-in-place, and (with limits) an agent.

## 1. Prepare Ollama (once, online)
```
ollama pull qwen2.5-coder:1.5b      # autocomplete (fast)
ollama pull qwen2.5-coder:7b        # chat/edit (smarter, slower on 4 GB GPU)
ollama pull nomic-embed-text        # lets @codebase search your project
```
After this, nothing needs the internet.

## 2. Install the extension
VS Code → Extensions → search **Continue** (publisher: Continue) → Install. Open it from the sidebar icon.

## 3. Config: `~/.continue/config.yaml`
```yaml
name: Local
version: 1.0.0
schema: v1
models:
  - name: Qwen Coder 7B (chat)
    provider: ollama
    model: qwen2.5-coder:7b
    roles: [chat, edit, apply]
  - name: Qwen Coder 1.5B (fast)
    provider: ollama
    model: qwen2.5-coder:1.5b
    roles: [chat, edit, autocomplete]
  - name: Nomic Embed
    provider: ollama
    model: nomic-embed-text
    roles: [embed]
context:
  - provider: code
  - provider: docs
  - provider: diff
  - provider: terminal
  - provider: codebase
```
Switch the model in the Continue chat box dropdown. Older Continue versions use `config.json`; the extension offers to migrate.

## 4. Stay offline and private
- VS Code settings → search `continue telemetry` → turn it off.
- Do not sign in to Continue Hub; use only the local config above.
- Check: disconnect Wi-Fi, ask a question in chat. It should still answer.

## 5. Your 4 GB GPU
- 1.5B fits fully on the GPU. 7B spills to the CPU, so it is slower (this is why Plevel showed "x% GPU / y% CPU").
- Two models loaded at once compete for memory. If things crawl: use only the 1.5B for both autocomplete and chat, or set the 7B for chat and turn autocomplete off while you chat.
- Watch it in Plevel's sidebar monitor.

## 6. Simple vs complex projects
- **Simple (one or a few files):** `@file`, or select code and press Ctrl+L (chat) or Ctrl+I (edit). Works well on the 1.5B.
- **Complex (many files):** open the repo as the VS Code folder, ask with `@codebase`, and name files with `@file`. Small models lose track across many files, so ask about one feature or file at a time and give the error text.

## 7. Test plan: what can Continue do?
Run these in order in a scratch folder; note PASS/FAIL and speed.

1. **Autocomplete:** create `t.py`, type `def is_prime(n):` and pause. Does a sensible body appear? Tab accepts.
2. **Chat:** select a function → Ctrl+L → "Explain this". 
3. **Edit in place:** select a function → Ctrl+I → "add type hints and a docstring". Review the diff, accept or reject.
4. **Bug fix:** paste a traceback with `@terminal` → "why does this fail?"
5. **Tests:** select a function → "write pytest tests for this".
6. **Project question:** open the plevel repo → "@codebase where is the stop button handled?" (answer: `send_or_stop` in `main_window.py`).
7. **Multi-file change:** "@file main_window.py add a menu item that ..." Does the edit apply cleanly?
8. **Honesty trap:** "how do I use pandas.DataFrame.auto_clean_everything()?" Good = says it doesn't exist (the 1.5B failed this in Plevel).
9. **Agent mode** (mode switch in the chat box): "create a file hello.py that prints hello and run it". Agent mode needs a model that supports tool calling; qwen2.5-coder in Ollama is hit and miss here, so expect failures. If it fails, that is the model's limit, not your setup.

Send the results (or screenshots) to an AI assistant for a verdict.

## Expect
Strong: autocomplete, explaining code, small functions and refactors, docstrings, tests for small units.
Weak: large cross-file changes, long reasoning, anything needing current docs, reliable agent tool use, and confidently invented APIs. Always run the code.
