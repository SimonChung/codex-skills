# codex-skills

Windows 與 Mac 共用的私人 Codex 自訂技能儲存庫：[SimonChung/codex-skills](https://github.com/SimonChung/codex-skills)。技能原始檔集中在 `skills/`；每台電腦的個人技能目錄透過連結讀取同一份本機 checkout。

| 技能 | 用途 |
|---|---|
| `eisenhower-project-planning` | 專案、模組與子功能的優先序及實作狀態規劃 |
| `pdf-to-markdown` | 使用 Microsoft MarkItDown 轉換 PDF |
| `word-to-markdown` | 使用 Microsoft MarkItDown 轉換 Word DOCX |
| `sbom-security-check` | SBOM、依賴漏洞及交付安全檢查 |

只納入以上自訂技能及其腳本、參考資料、UI metadata；保留原有技能內容。Codex 內建技能、外掛、快取、聊天、登入資訊及專案程式碼不在此儲存庫。

## 安裝方式

需要 Git、Python 3.10 以上，以及能讀寫此私人儲存庫的 GitHub 認證。安裝／同步腳本只使用 Python 標準函式庫；Windows 另使用內建 PowerShell 或 PowerShell 7 建立 junction，不需要系統管理員權限。Mac 使用符號連結。

預設安裝到 `$CODEX_HOME/skills`，未設定時為 `~/.codex/skills`，與目前 Windows 及 Codex skill-installer 的位置一致。若你的 Codex 已使用 `~/.agents/skills`，可在以下 `install`、`sync`、`status` 命令都加上 `--dest ~/.agents/skills`；只選一個載入位置，避免同名技能重複出現。官方說明見 [Build skills](https://learn.chatgpt.com/docs/build-skills)。

### Windows PowerShell

首次下載至尚不存在的資料夾：

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE/projects" -Force | Out-Null
Set-Location "$env:USERPROFILE/projects"
git clone https://github.com/SimonChung/codex-skills.git
Set-Location codex-skills
python scripts/manage_skills.py install
python scripts/manage_skills.py status
```

### Mac 終端機

```sh
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/SimonChung/codex-skills.git
cd codex-skills
python3 scripts/manage_skills.py install
python3 scripts/manage_skills.py status
```

安裝完成後，下個 Codex 回合即可發現技能；若尚未顯示，重新開啟 Codex。此流程已在 Windows 驗證；POSIX 連結行為另以 Linux 隔離測試驗證，不能當作 Mac 原生實機驗收。

## 已有同名技能時

安裝程式先檢查全部目的資料夾，再執行遷移：

- 已正確連到本 checkout：不變更，可重複執行。
- 既有資料夾與儲存庫內容相同：先完整移至個人技能目錄旁的 `skill-backups/codex-skills/<時間-識別碼>/`，再建立連結；保留原有 Python 快取。比較文字檔時容許 LF／CRLF 差異。
- 既有檔案有內容差異，或連結指向其他位置：停止並保留現況。先比對並把需要保留的修改整合到 `skills/<名稱>/`，確認後再安裝；沒有強制覆蓋模式。

安裝結果會列出備份位置，備份內另有 `migration.json`。備份放在技能掃描目錄外，避免被當成另一個技能載入。不要移動或刪除已被連結的 checkout；若要搬位置，先規劃重設連結。

## 每次換電腦

開始工作前，在本儲存庫執行：

```powershell
# Windows
python scripts/manage_skills.py sync
```

```sh
# Mac
python3 scripts/manage_skills.py sync
```

`sync` 要求目前為追蹤 `origin/main` 的 `main` 分支、工作區乾淨，且沒有未推送提交。它先 fetch，以 fast-forward 更新，再檢查／安裝技能連結。技能原有連結會直接讀到新檔案；新增技能也會安裝。遇到未提交修改、分歧、其他來源的同名技能或網路錯誤會停止，不覆蓋、不自動 stash、不 force push。

修改技能後，先完成驗證，再檢查、選擇本次檔案暫存，使用繁體中文提交訊息並推送。例如已暫存本次差異時：

```sh
git diff --cached --check
git commit -m "更新通用技能使用說明"
git push origin main
```

這是雙向的 Git 交換流程：Windows 修改推送後，Mac 執行 sync；Mac 修改推送後，Windows 執行 sync。直接修改個人技能目錄內已連結的檔案，也會改動本儲存庫，記得提交。

本儲存庫獨立於 BeaconAR，拉取 BeaconAR 不會同步它。可以對 Codex 說：「開始前先同步 codex-skills，再同步 BeaconAR。」這裡沒有建立背景排程，也不會在未驗證時自動上傳技能修改。

## 技能檔案與執行環境

技能同步不會安裝轉檔引擎、Docker、MCP、雲端服務、憑證或整份 Codex 設定。PDF／Word 技能仍依各自 `SKILL.md` 尋找 Codex bundled Python 及 MarkItDown；缺少工具時須依該環境安裝或回報。

兩個轉檔 wrapper 是跨平台 Python；PowerShell 範例中的 `<bundled-python>` 在 Mac 亦需替換為實際的 bundled Python 路徑，用一般 shell 呼叫。SBOM 的 Go／Node／Docker 參考文件仍保留其 Windows PowerShell 範例，實際命令依被檢查專案的平台調整。

安裝／同步測試：

```sh
python -m unittest discover -s tests -v
```

依賴及 SBOM 的範圍、重跑命令與限制見 [security/README.md](security/README.md)。
