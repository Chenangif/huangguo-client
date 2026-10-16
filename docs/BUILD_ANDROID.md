# 构建 Android APK（Windows 原生，无需 WSL）

> 原计划的 Kivy + Buildozer 路线需要 WSL；本机 `wsl.exe` 被安全策略拦截，
> 改用 **Windows 原生 Gradle + Android SDK**，功能不受影响。

## 1. 安装 JDK 17

```powershell
winget install -e --id Microsoft.OpenJDK.17 --accept-source-agreements --accept-package-agreements
```

安装后路径形如 `C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot`（下面用 `$JDK` 代称）。

## 2. 安装 Android SDK

下载 commandline-tools（约 130MB）：
```
https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip
```

解压后放到 `C:\Android\sdk\cmdline-tools\latest\`（目录结构必须是 `...\latest\bin\sdkmanager.bat`）。

接受许可：
```bat
set JAVA_HOME=%JDK%
C:\Android\sdk\cmdline-tools\latest\bin\sdkmanager.bat --licenses --sdk_root=C:\Android\sdk
```

安装组件（约 1GB，建议后台跑）：
```bat
set JAVA_HOME=%JDK%
C:\Android\sdk\cmdline-tools\latest\bin\sdkmanager.bat --sdk_root=C:\Android\sdk ^
  platform-tools platforms;android-34 build-tools;34.0.0
```

## 3. 安装 Gradle 8.7

官方源很慢（~100KB/s），**用腾讯云镜像（约 11MB/s）**：
```
https://mirrors.cloud.tencent.com/gradle/gradle-8.7-bin.zip
```
解压到 `C:\Android\gradle-8.7`。

## 4. 配置 SDK 路径

在 `android/local.properties` 里写（该文件已在 .gitignore 中，不会入库）：

```properties
sdk.dir=C:\\Android\\sdk
```

## 5. 构建

```bat
cd android
set JAVA_HOME=%JDK%
set ANDROID_SDK_ROOT=C:\Android\sdk
set GRADLE_USER_HOME=C:\Android\.gradle
C:\Android\gradle-8.7\bin\gradle.bat --no-daemon assembleDebug
```

产物：`android\app\build\outputs\apk\debug\app-debug.apk`。

---

## 依赖与镜像

Maven 仓库已在 `settings.gradle` 中按 `阿里云 → google() → mavenCentral()` 排序，国内下载快。

主要依赖：
- `androidx.media3:media3-exoplayer:1.4.1`
- `androidx.media3:media3-exoplayer-hls:1.4.1`
- `androidx.media3:media3-ui:1.4.1`
- `androidx.appcompat:appcompat:1.7.0` / `recyclerview:1.3.2` / `constraintlayout:2.1.4`
- `com.google.android.material:material:1.12.0`
- `com.squareup.okhttp3:okhttp:4.12.0`

## ⚠️ Media3 HLS 模块坐标

HLS 支持的正确坐标是 **`androidx.media3:media3-exoplayer-hls`**。
写成 `androidx.media3:media3-hls` 会在任何仓库都找不到，构建直接报 `Could not find`。

## ⚠️ setControllerVisibilityListener 二义性

`PlayerView.setControllerVisibilityListener` 有两个重载（来自 `PlayerView.ControllerVisibilityListener`
与 `PlayerControlView.VisibilityListener`），用 lambda 会编译失败，必须写显式匿名类：

```java
playerView.setControllerVisibilityListener(new PlayerView.ControllerVisibilityListener() {
    @Override public void onVisibilityChanged(int visibility) { ... }
});
```

---

## 发布前：签名

当前是 debug 签名，仅供自用。若要发布 release，在 `app/build.gradle` 配置 `signingConfig`
（用 `keytool` 生成 keystore），再执行 `assembleRelease`。
