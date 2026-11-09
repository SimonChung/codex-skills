# Go／Node／Docker 執行要點

只有專案包含相關技術時讀取／套用本頁；這是建立或檢查流程的參考，不是可不經修改直接部署的腳本。

## 優先沿用現有流程

用 `rg --files` 找 `AGENTS.md`、鎖檔、Dockerfile、Compose、CI 與 `scripts/*sbom*`／`scripts/*security*`。確認腳本是否會建置、改標籤或部署，及其門檻是否符合本次要求。

例如已有 PowerShell 腳本時，從專案目錄執行並檢查子程序狀態：

```powershell
pwsh -NoProfile -File ./scripts/verify-sbom.ps1
$scanExit = $LASTEXITCODE
if ($scanExit -ne 0) { throw 'SBOM／漏洞檢查未通過' }
```

先讀該腳本確認是否需要參數。既有程式若直接發布、重啟或推播，不能只因要檢查就順帶執行這些操作。

## 來源清單與 npm

- 掃描目錄保留相對路徑，只複製必要 manifest／鎖檔；例如 `go.mod`、`go.sum` 及各個 npm workspace 的 `package.json`／`package-lock.json`。偵測 workspace，不能假定前端都在 `web/`。
- Node 版本沿用實際建置工具鏈。純 Node 專案可以只做來源／建置產物檢查；不要為了這個技能加 Docker。
- npm audit 使用 `--package-lock-only --include=dev --audit-level=high --json`；檢查回傳值、JSON 是否有 `error`，以及完整的 `metadata.vulnerabilities`。它會向設定的 registry 送出相依資訊，不擅自改用另一個服務。
- `npm ci --no-audit` 後接 `npm audit --audit-level=high` 可作為 Docker build 的額外門檻。該 RUN layer 可能命中快取，不能取代每次獨立執行的漏洞掃描。

以下為在受控掃描環境內的 Trivy 命令形狀，先確認固定工具版本支援這些旗標。`/inputs` 僅放核准的 manifest，`/reports` 是新的輸出目錄：

```sh
trivy fs --include-dev-deps --format cyclonedx --output /reports/source.cdx.json /inputs
trivy sbom --scanners vuln --severity HIGH,CRITICAL --exit-code 1 --format json --output /reports/source-vulnerabilities.json /reports/source.cdx.json
```

Trivy 的 `--include-dev-deps` 很重要：只看到 Vite 不代表 TypeScript、測試工具及其他開發相依都在 SBOM。核對 manifest 的直接與開發相依；必要時檢查鎖檔中可辨識的間接相依。npm 的 scoped purl 可能將 `@` 編碼為 `%40`，須正規化後比較。

不要把舊報告或既有 `.trivyignore` 不明套用到新掃描。使用隔離工作目錄；若沒有核准例外，可在 Linux 掃描容器明確指定空的 ignore file，例如 `--ignorefile /dev/null`。Windows 原生工具應使用實際存在的空檔，不能照抄 `/dev/null`。

## Go

- 來源 SBOM 確認包含模組相依，結果中確認有 Go module 類別。使用 `go mod tidy` 後重新核對，避免舊的未使用相依仍被留在清單中。
- 正式執行檔再核對編譯器／標準函式庫與實際連入的模組；來源鎖檔掃描不能取代二進位掃描。
- `go mod verify`、`go test ./...`、`go vet ./...` 及專案需要的整合測試各有不同用途。資料庫測試沿用專案隔離方式，不對正式資料執行測試 migration。
- 需要可達性分析時可使用官方 `govulncheck`，固定已核實的工具版本，並依正式平台設定進行 source 或 binary 模式分析；保留它與版本掃描結果的區別。

## 正式映像

建置新的候選標籤，記錄 image ID，匯出該映像而非執行中容器的環境設定：

```sh
docker image save --output image.tar candidate-image
trivy image --input image.tar --format cyclonedx --output image.cdx.json
trivy sbom --scanners vuln --severity HIGH,CRITICAL --exit-code 1 --format json --output image-vulnerabilities.json image.cdx.json
```

- 容器化掃描器使用已核實的 `版本@digest`，只掛載所需輸入、報告目錄與專用 DB cache。上面的命令需要改成容器內實際路徑，並在宿主保存報告。
- 從當前映像辨識 Ubuntu、Debian、Alpine 或 scratch；依應有套件檢查 SBOM purl 及掃描報告的 OS／語言類別。不能把「未支援／未識別 OS」當作 0 項漏洞。
- 預設正常更新漏洞資料庫，記錄 metadata 時間；不能以 `--skip-db-update` 掩蓋網路問題。若使用者要求離線分析，標示離線資料日期與限制，缺 DB 時不能宣稱通過。
- 原生 Trivy、容器掃描或專案現有工具都可以使用。選擇能產生完整證據且符合既有環境的方式，不強迫使用特定 host OS。

## PowerShell 與失敗處理

- 使用 PowerShell 7 並固定 UTF-8 JSON 輸出；`ConvertFrom-Json -AsHashtable` 可處理 npm 鎖檔中名稱為空字串的根套件。
- 啟用 `Set-StrictMode` 時，可選欄位以字典索引搭配結構驗證取值，例如 `$report['error']`，避免缺欄位誤當成功或意外中止。
- 每個外部命令執行後立即保存 `$LASTEXITCODE`；JSON stdout 與診斷 stderr 分開保存。不要在另一個成功命令後才讀取前一個命令的退出碼。
- 只有確定工具的退出語意且完整解析報告後，才把特定非 0 狀態解釋成「找到漏洞」；其他情況一律為未完成。最外層命令仍須以非 0 回傳。
- 當次狀態先寫為 incomplete，失敗保留原因及現有報告；所有必需掃描通過後才能變成 passed。若涉及映像標籤，兩個負向測試都應確認原標籤沒有改變。

## 官方參考

版本與旗標可能變動，需要調整時回到官方文件核實：

- [Trivy：SBOM 產生與掃描](https://trivy.dev/docs/latest/supply-chain/sbom/)
- [npm audit](https://docs.npmjs.com/cli/v11/commands/npm-audit/)
- [npm sbom](https://docs.npmjs.com/cli/v11/commands/npm-sbom/)
- [Go govulncheck](https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck)
- [Docker：多階段建置與 SBOM 範圍](https://docs.docker.com/build/metadata/attestations/sbom/)
