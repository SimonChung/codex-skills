# Flutter、Kotlin 與 Swift 套件檢查

先確認這次交付哪些應用、平台與建置組態，再從其套件清單找出對應鎖檔。以下命令從本技能目錄執行，每份鎖檔使用新的報告目錄。只執行目標實際使用的套件管理器，排除第三方 checkout、`Pods/`、`.build/`、`.dart_tool/`、建置產物及無關範例。同一份鎖檔被多個平台或技能流程引用時，可共用當次結果並記錄適用範圍。

| 目標 | 掃描輸入與方式 |
|---|---|
| Flutter／Dart | 從 `pubspec.yaml` 找出本次解析的 `pubspec.lock`，Pub workspace 使用根鎖檔。檢查 hosted 套件的直接、開發與間接相依。Flutter 的 Android 外掛另查 Gradle，iOS／macOS 外掛另查實際的 SwiftPM 或 CocoaPods。 |
| Kotlin | Kotlin/JVM、Android 的 `build.gradle(.kts)` 或 `pom.xml` 沿用 [Gradle／Maven 檢查](java.md)，包含 Kotlin 標準函式庫。多平台專案依此次建置的 source sets、targets、variants 及測試 configurations 核對鎖定範圍。Kotlin/JS 有 npm／Yarn 鎖檔時另查 JS 相依，Apple targets 有 SwiftPM／Pods 時另查對應鎖檔。直接引入的 KLIB 或 C interop 二進位須依產物辨識來源與版本。 |
| SwiftPM | 掃描 Swift 套件的 `Package.resolved` 或實際 Xcode workspace／project 的 `xcshareddata/swiftpm/Package.resolved`，支援 v1、v2、v3。按來源儲存庫與發行版本核對。對本地 Swift packages 另檢查其來源與該次建置的相依圖。 |
| CocoaPods | 掃描實際安裝所用的 `Podfile.lock`，保留 pod 與 subspec。CocoaPods 公告可能以整個來源儲存庫比對，命中後核對受影響的 subspec。 |

```sh
python3 scripts/scan_mobile_lock.py app/pubspec.lock reports/pub
python3 scripts/scan_java.py app/android/app/gradle.lockfile reports/kotlin-android
python3 scripts/scan_mobile_lock.py app/ios/Runner.xcworkspace/xcshareddata/swiftpm/Package.resolved reports/swiftpm
python3 scripts/scan_mobile_lock.py app/ios/Podfile.lock reports/pods
```

Pub 與 CocoaPods 需要能匯入 PyYAML 的 Python 3.10 以上環境。此儲存庫的驗證環境已固定 PyYAML 版本。SwiftPM 使用 Python 標準函式庫。掃描器使用 Trivy CLI，或以 `--trivy-image` 指定專案核准且固定 digest 的 Docker 映像。

核對 CycloneDX、漏洞報告與鎖檔中的公開套件名稱和版本。預設門檻為 HIGH、CRITICAL，可用 `--severity` 調整。回傳 0 表示通過、沒有鎖定的外部套件或不適用，1 表示命中門檻，2 表示檢查未完成。來源或版本未核實時，摘要列出缺口並保留已確認的漏洞。SDK 綁定的 Pub 套件另列於 `sdkPackages`。Flutter／Dart SDK 本身需依實際建置的 SDK 版本查核。

依現有建置證據核對 Pub／Pods 的本地、Git 或私有來源，以及只有 branch／revision 的 Swift pin。保留原始 revision 和鎖檔雜湊。專案若只有 manifest、版本目錄或未涵蓋交付 target 的鎖檔，從相同提交與建置設定取得實際解析結果。若專案確實沒有第三方相依，可用建置工具輸出的空相依圖記錄此情形。

[Trivy 的 Pub 支援](https://trivy.dev/docs/v0.76/guide/coverage/language/dart/) · [Trivy 的 SwiftPM 與 CocoaPods 支援](https://trivy.dev/docs/v0.76/guide/coverage/language/swift/) · [Kotlin Multiplatform 的 source sets 與 targets](https://kotlinlang.org/docs/multiplatform/multiplatform-discover-project.html)
