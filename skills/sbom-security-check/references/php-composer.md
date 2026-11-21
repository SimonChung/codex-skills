# PHP Composer 套件漏洞檢查

在本次交付範圍內找出各自維護 Composer 相依的模組，包括 monorepo 的子目錄。對每個模組使用其自身的鎖檔，涵蓋 `packages`、`packages-dev` 與兩者的間接相依。來源檢查與正式部署映像的已安裝套件應分開記錄。

沿用目標專案已能涵蓋上述範圍的驗證流程。若需要可重複的預設檢查，使用技能隨附的 `scripts/scan_composer.py`、Python 3.10 以上及專案核准版本的 Trivy CLI。以下從本技能目錄執行，傳入一個 Composer 模組及本次報告的新目錄。

```sh
python3 scripts/scan_composer.py /path/to/php-module /path/to/reports/php-module-run
```

- 若專案透過 Docker 使用 Trivy，在同一命令加上 `--trivy-image <映像名稱>@sha256:<digest>`。容器只掛載暫存的 Composer 輸入、當次報告目錄及可重用的 Trivy 快取。若已有核准的漏洞例外，沿用專案的驗證流程並列出例外。
- 腳本只讀取該模組的 Composer 檔案。兩檔皆無時回報略過。只有 manifest 而沒有鎖檔時，回報缺少鎖定版本；對刻意不提交鎖檔的函式庫，可使用該次受測建置產生的鎖檔。若兩檔齊全，可用 `composer --no-plugins validate --check-lock --no-check-publish` 確認鎖檔符合 manifest。
- 有鎖定套件時，腳本以 `--include-dev-deps` 掃描，保存漏洞 JSON、CycloneDX、輸入檔 SHA-256 及 Trivy／漏洞資料庫版本。兩份報告都須涵蓋鎖定的名稱與版本。空鎖檔會記為 `no-locked-packages`，若 manifest 仍宣告外部套件則回報檢查未完成。正常完成或略過回傳 0，命中門檻回傳 1，工具失敗、缺檔或涵蓋不完整回傳 2。預設門檻是 HIGH、CRITICAL，可用 `--severity` 套用專案規定，例如 `--severity MEDIUM,HIGH,CRITICAL`。
- 開發分支或私有套件的公告覆蓋率可能有限。PHP 執行環境及擴充模組依部署產物另行盤點；原始碼弱點屬於程式碼分析範圍。

[Trivy 的 Composer 支援](https://trivy.dev/docs/v0.76/guide/coverage/language/php/) · [Composer 鎖檔與平台相依](https://getcomposer.org/doc/01-basic-usage.md)
