# Switch 接続機能 セットアップガイド

## 必要環境

### Python (必須)
- Python 3.9 以上
- `pip install pybluez` (Bluetooth ライブラリ)

### Windows の場合
1. [Python 3.x](https://www.python.org/) をインストール
2. Bluetooth スタックのインストール:
   ```
   pip install pybluez
   ```
3. Bluetooth アダプターが **Bluetooth Classic (BR/EDR)** に対応していること  
   ※ BLE Only のアダプターでは動作しません

4. `socket.AF_BLUETOOTH` が使えるか確認:
   ```python
   python -c "import socket; s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP); print('OK')"
   ```

## ペアリング手順

1. **Switch 本体** → 設定 → コントローラーとセンサー → コントローラーの持ち方/順番を変える を開く
2. PC の Bluetooth を ON にする  
3. Switch の MAC アドレスを確認（設定 → 本体 → Bluetooth）
4. ツールの「Switch接続」タブを開く
5. MAC アドレスを入力して「接続」をクリック
6. Switch がコントローラーとして認識されるまで待つ（10〜30秒）

> ⚠️ 初回ペアリング時は Switch 側で「Pro コントローラー」として表示されます。

## マクロ機能

1. ボタンを選択（複数選択可）
2. 継続時間を設定（ms）
3. 「＋ 追加」でステップを積み上げる
4. 「マクロ名」を入力して「保存」
5. 「▶ 現在のステップ実行」または保存済みマクロの「▶」で実行
6. 「ループ」チェックボックスで無限ループも可能

## ファイル構成

```
mhxx_Snipe.exe-main/
├── main.js           ← 更新済み (IPC + Python 起動)
├── package.json      ← 更新済み (extraResources)
└── src/
    ├── index.html    ← 更新済み (Switch接続タブ追加)
    ├── preload.js    ← 新規 (BT API ブリッジ)
    └── switch_bt.py  ← 新規 (Pro Controller HID エミュレーター)
```

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| 「接続失敗」エラー | Switch が検出モードになっているか確認 |
| Python が見つからない | PATH に python を追加、または python3 でシンボリックリンク |
| AF_BLUETOOTH エラー | pybluez の再インストール、または管理者権限で実行 |
| 接続はするが操作が効かない | Switch を再起動して再ペアリング |
