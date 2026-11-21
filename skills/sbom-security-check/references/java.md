# Java 套件漏洞檢查

在本次交付範圍內找出 Maven reactor 根目錄、獨立 Maven 專案及 JVM／Android 的 Gradle 子專案。沒有這些建置時，略過 Java 檢查。沿用目標專案已核准且涵蓋所需版本與範圍的流程。需要預設流程時，從本技能目錄執行下列命令，每次使用新的報告目錄。

## Maven

```sh
python3 scripts/scan_java.py /path/to/project/pom.xml /path/to/reports/maven-run
```

腳本使用 POM 同目錄的 Maven Wrapper 或系統 `mvn`。它呼叫 Dependency Plugin 產生各模組的相依樹，並以 CycloneDX Plugin 產生包含測試相依的 SBOM。Maven 會解析父 POM、匯入的 BOM、屬性、版本衝突及間接相依。單獨解析 POM 的 Trivy 模式會略過部分 Maven scopes 與 optional 相依。[Trivy Java 支援範圍](https://trivy.dev/docs/v0.76/guide/coverage/language/java/)

沿用實際建置的 JDK、settings、套件庫與 profiles，例如加入 `--maven-arg=-Pproduction`。在同一個 checkout 驗證，每個交付組態分開保存結果。從多模組根目錄執行一次，各參與模組會有獨立的相依樹、CycloneDX 與掃描狀態。只有 `dependencyManagement` 宣告且未被任何模組引用的套件，不計入該模組的已解析相依。[Maven 相依樹](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) · [CycloneDX Maven Plugin](https://cyclonedx.github.io/cyclonedx-maven-plugin/makeBom-mojo.html)

## Gradle

```sh
python3 scripts/scan_java.py /path/to/module/gradle.lockfile /path/to/reports/gradle-run
```

逐一掃描交付範圍內的 `*gradle.lockfile`，包括適用的 buildscript 鎖檔。腳本會納入測試相依並核對每個鎖定版本。確認鎖檔涵蓋實際交付的 configurations、Android variants 與測試組態。僅有 `build.gradle`、`build.gradle.kts` 或版本目錄時，沿用專案的建置流程取得該組態的已解析相依與 SBOM，再核對並掃描。缺少解析證據時回報「檢查未完成」。[Gradle 相依鎖定](https://docs.gradle.org/current/userguide/dependency_locking.html)

## 判讀結果

預設以原生 Trivy 執行。有核准的 Docker 工具映像時，可加 `--trivy-image <映像名稱>@sha256:<digest>`。漏洞門檻預設為 `HIGH,CRITICAL`，可用 `--severity` 套用專案政策。

檢查逐一核對 Maven 的 groupId、artifactId、version 是否同時出現在已解析清單、CycloneDX 及漏洞掃描結果。回傳 0 表示通過、沒有外部相依或不適用，1 表示命中門檻，2 表示解析失敗、缺少輸入或報告不完整。報告目錄內有 `summary.json`，Maven 另有建置日誌與每個模組的結果。若交付 JAR、WAR 或容器，依實際產物另行檢查打包內容及 JRE／OS。Maven 建置外掛和未納入鎖檔的 Gradle 組態須依實際使用情形另行盤點。
