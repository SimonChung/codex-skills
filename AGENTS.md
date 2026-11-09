# codex-skills 維護規範

- Git commit message 使用繁體中文，簡要描述變更。新工作分支使用 `codex/` 前綴。
- 本儲存庫只管理 `skills.json` 列出的通用自訂技能及安裝／驗證流程；不要加入 Codex `.system`、外掛快取、登入憑證、聊天紀錄或其他個人設定。
- 修改技能時，先讀既有技能、被引用資源及實際呼叫者，保留原用途與使用者授權範圍。使用 skill-creator 的結構驗證；安裝流程有變更時執行 `python -m unittest discover -s tests -v`。
- 開始修改前先檢查工作區及 upstream；乾淨時以 `git pull --ff-only` 同步。保留既有修改，不強制覆蓋或夾帶無關提交。
- 兩台電腦的已安裝技能以連結指向本儲存庫；直接修改已安裝技能也會改動版控來源。提交前檢查完整 diff，不以安裝複本當作第二份來源。
- 使用者要求發布變更時，通過適用驗證後提交並推送。`scripts/manage_skills.py sync` 只拉取、檢查與安裝，不會代替 commit／push，也不建立背景排程。
- Dependency 要通過 SBOM 驗證。安裝／同步程式只用 Python 標準函式庫；轉檔技能的外部執行環境和驗證工具見 `security/README.md`。不要把技能檔案同步成功當作外部工具、Mac 原生執行或目標文件轉檔已驗證。
- 若有資料庫，Table PK 使用 UUID，禁止 SEQUENCE。
