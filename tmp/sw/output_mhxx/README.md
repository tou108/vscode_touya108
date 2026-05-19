# MHXX 護石スナイプツール - ビルド手順

## 必要なもの
- **Node.js** (v18以上推奨): https://nodejs.org/ja/ からインストール
- **Git** (任意): https://git-scm.com/

---

## ビルド手順

### 1. このフォルダをPCに配置
このフォルダ（`mhxx_snipe_app`）をWindowsのデスクトップや任意の場所に置いてください。

### 2. `assets` フォルダにアイコンを用意（任意）
`assets/icon.ico` にアプリのアイコンファイルを置くと、exeにアイコンが設定されます。
不要な場合は `package.json` の `"icon": "assets/icon.ico"` の行を削除してください。

### 3. コマンドプロンプト（またはPowerShell）を開く
このフォルダを右クリック →「ターミナルで開く」または「PowerShellで開く」

### 4. パッケージのインストール
```
npm install
```
（数分かかる場合があります）

### 5. exeのビルド
```
npm run build
```

### 6. 完成！
`dist` フォルダの中に以下が生成されます：
- `MHXX護石スナイプツール Setup x.x.x.exe` → インストーラー版
- `MHXX護石スナイプツール_portable.exe` → インストール不要のポータブル版（1ファイルで動く）

---

## GitHubへのアップロード（任意）

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/tou108/mhxx_Snipe.exe.git
git push -u origin main
```

---

## 動作テスト（ビルド前に確認したい場合）
```
npm start
```
これでElectronウィンドウが開いてアプリが起動します。

---

## フォルダ構成
```
mhxx_snipe_app/
├── main.js          ← Electronのメインプロセス
├── package.json     ← ビルド設定
├── README.md        ← この手順書
├── src/
│   └── index.html   ← アプリ本体
└── assets/
    └── icon.ico     ← アイコン（任意）
```
