# 驗證環境與 SBOM

安裝／同步程式 `scripts/manage_skills.py` 只使用 Python 標準函式庫，另呼叫本機 Git；Windows 連結建立使用 PowerShell。安裝技能檔案不會安裝 Python 套件或變更 Codex bundled runtime。

兩個轉檔技能既有的 wrapper 會在使用時載入 Microsoft MarkItDown。為驗證這份技能集合，使用 `.work/validation-venv` 隔離環境安裝：

- `PyYAML==6.0.3`：執行 Codex skill-creator 提供的 `quick_validate.py`。
- `markitdown[docx,pdf]==0.1.9`：載入既有轉檔 wrapper 所需的依賴，不啟用雲端轉檔或 OCR。

直接需求見 `requirements-validation.in`；`requirements-validation.txt` 是由實際隔離環境的 `pip freeze --all` 產生的完整套件版本快照，包含間接依賴與 pip。它不是使用者所有 Python 環境的清單，也不表示 Mac 已安裝相同版本。

## 重建隔離驗證環境

Windows：

```powershell
python -m venv .work/validation-venv
.work/validation-venv/Scripts/python.exe -m pip install -r security/requirements-validation.txt -r security/requirements-validation.in
.work/validation-venv/Scripts/python.exe -m pip check
python -m unittest discover -s tests -v
python scripts/verify_sbom.py
```

Mac 需要另行實機驗收；使用 `python3` 與 `.work/validation-venv/bin/python` 對應上述命令。如果平台無法安裝同一版本組合，先核對上游支援，重新解析並產生該平台版本快照，再以 `--requirements` 掃描它，不沿用 Windows 的通過結論。

需要重新驗證技能結構時，使用該台 Codex 內建 skill-creator 的 `scripts/quick_validate.py`，對 `skills.json` 中每個資料夾執行。此驗證器不是本儲存庫的自訂技能，不複製 Codex `.system` 內容。

## 掃描流程與阻擋條件

`python scripts/verify_sbom.py` 使用本機 Docker 執行固定的 Trivy `0.76.2` 映像及多架構 digest `sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb`。只掛載必要的依賴快照及本次報告目錄，先產生 CycloneDX，再掃描 HIGH／CRITICAL；不忽略未修復漏洞，不使用忽略清單，不上傳技能內容或使用者文件。

除了檢查 scanner 回傳碼，還逐項比對 CycloneDX 的 PyPI 名稱／版本與完整快照，拒絕缺漏套件、缺掃描報告、未識別依賴生態、驗證期間快照被修改、scanner 失敗及 HIGH／CRITICAL 命中。每次在 `.work/security/<時間-識別碼>/` 保存 SBOM、JSON 報告、日誌、資料庫時間及成功或失敗摘要。

測試包含實際安裝／Git 同步行為、正常報告、High 命中、清單缺漏、缺報告及 scanner 錯誤；安全測試中的模擬輸入是驗證阻擋邏輯，不能當作真實掃描證據。正式驗證另執行真實 Trivy 掃描。

範圍不包含主機 OS、Python 執行檔／標準函式庫、Git、PowerShell、Codex bundled runtime、Mac 原生環境、scanner 映像本身，或未來使用 SBOM 技能時會檢查的其他專案。技能中的 Docker／npm／Go 工具依當次目標專案另行驗證。

初次發布的 [2026-11-10 驗證摘要](verification-20261110.json) 記錄技能結構、Windows／POSIX 測試與 31 個驗證環境套件的 SBOM 結果；另以 `urllib3==1.26.5` 真實掃描確認 High 漏洞會回傳非 0 並阻擋通過。

Trivy 0.76.2 升級後的 [2026-11-11 驗證摘要](verification-20261111.json) 記錄 macOS 上的 12 項測試、31 個固定套件的重新掃描與已知 High 套件的拒絕結果；未重新安裝完整 Windows 驗證環境，也未重跑 Windows 測試。

## 每週 SBOM 工具版本檢查

[Project tool versions](https://github.com/SimonChung/codex-skills/actions/workflows/sbom-tool-versions.yml) 在 GitHub-hosted Ubuntu runner 執行，排定每週一 UTC 01:00（台北 09:00）；GitHub 排程可能延遲，Mac 不需要開機。也可用 Actions 的 Run workflow 手動觸發，勾選 `dry_run` 時只預覽、不建立 Issue。

巡檢已擴充至本專案實際使用的 Trivy、Git、Python、PowerShell、Docker Engine／Desktop，以及固定的 MarkItDown、PyYAML、pip。沒有使用 Go，因此仍略過 Go。版本來源、未固定工具的發布追蹤、安全修補線索、通知去重及本機驗證方式，統一見[共用巡檢說明](../.github/SBOM_TOOL_MONITOR.md)。這是工具版本通知，不取代上方 31 個驗證環境套件的 SBOM；沒有新增 Python 第三方依賴。

## 來源

- [Microsoft MarkItDown](https://pypi.org/project/markitdown/)
- [PyYAML](https://pypi.org/project/PyYAML/)
- [Trivy Python 套件辨識](https://trivy.dev/docs/latest/coverage/language/python/)
- [GitHub Actions 排程事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GITHUB_TOKEN 最小權限](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)
