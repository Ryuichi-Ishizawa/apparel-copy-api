# Apparel Copy API

商品画像から EC 用のテキスト（商品名・説明文・カテゴリ・タグ）を自動生成する FastAPI。Claude AI を使用して、画像の視覚情報と任意の補足情報から、ブランド感を保った日本語コピーを生成します。

## 特徴

- **画像認識 → テキスト生成** … 複数の商品画像から、EC に掲載できる商品説明文を自動作成
- **補足情報の抽出** … 仕入れ元ページ（英語テキスト）から、素材・サイズ・価格などの事実情報を自動抽出・日本語化
- **高い品質管理** … 画像から判断できない項目を `uncertain` 欄に保留、補足情報と画像の矛盾を `conflicts` で検出
- **テスト完備** … pytest による自動テスト（認証・エラーハンドリング）が全て PASSED
- **API キー認証** … リクエストのセキュリティを保証

## セットアップ

### 前提条件

- Python 3.10 以上
- 環境変数 `ANTHROPIC_API_KEY` を設定済み（Claude API キー）
- 環境変数 `APP_API_KEY` を設定済み（API アクセス用の合言葉）

### インストール

```bash
# リポジトリをクローン
git clone <このリポジトリの URL>
cd apparel-copy-api

# 仮想環境を作成
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存パッケージをインストール
pip install fastapi uvicorn python-multipart anthropic pytest pytest-asyncio httpx
```

### 環境変数の設定

```bash
# .env ファイルを作成（またはシェルで直接設定）
export ANTHROPIC_API_KEY="sk-..."  # Claude API キー
export APP_API_KEY="my-secret-key-123"  # API 認証用キー（任意の文字列）
```

## 起動

```bash
uvicorn api:app --reload --port 8000
```

起動後、ブラウザで http://127.0.0.1:8000/docs を開くと、Swagger UI が表示され、そこから直接 API を試せます。

## 使い方

### 1. 画像から商品コピーを生成

**リクエスト例（curl）**

```bash
curl -X POST "http://127.0.0.1:8000/generate-copy" \
  -H "X-API-Key: my-secret-key-123" \
  -F "images=@product.jpg" \
  -F "gender=auto" \
  -F "revise=true"
```

**パラメータ**

| 名前 | 型 | 説明 | デフォルト |
|------|-----|------|----------|
| `images` | file (複数可) | 商品画像（JPG/PNG/WebP） | 必須 |
| `gender` | string | ターゲット: `auto`, `mens`, `ladies` | `auto` |
| `known_facts` | string | 補足情報（素材・サイズ・価格など） | 空 |
| `brand_notes` | string | ブランド・店舗補足 | 空 |
| `revise` | boolean | 自己添削を行うか | `true` |

**レスポンス例**

```json
{
  "visible_facts": "ネイビー(濃紺)の中綿入りキルティングジャケット。...",
  "product_name": "ノーカラー キルティング中綿ジャケット",
  "description": "深みのあるネイビーが上品なノーカラーキルティングジャケットです。...",
  "category": "アウター > ブルゾン・デニムジャケット",
  "tags": ["ネイビー", "キルティング", "中綿ジャケット", ...],
  "uncertain": ["素材混率(表地・中綿の詳細)", "サイズ展開", "ブランド名", ...],
  "conflicts": []
}
```

**フィールド説明**

- `visible_facts` … 画像から読み取った詳細情報（内部用）
- `product_name` … 生成された商品名
- `description` … EC 掲載用の説明文（文体ルール準拠）
- `category` … 商品カテゴリ
- `tags` … 検索・フィルタリング用タグ
- `uncertain` … 画像から断定できず保留した項目（確認推奨）
- `conflicts` … 補足情報と画像の矛盾（修正推奨）

### 2. 仕入れ元ページから補足情報を抽出

**リクエスト例**

```bash
curl -X POST "http://127.0.0.1:8000/extract-facts" \
  -H "X-API-Key: my-secret-key-123" \
  -F "source_text=Material: Cotton 80% Polyester 20% / Size: XS,S,M,L / Price: $120"
```

**レスポンス例**

```json
{
  "known_facts_ja": "素材: コットン80% ポリエステル20% / サイズ: XS,S,M,L / 価格: $120",
  "not_found": []
}
```

### 3. ブラウザから対話的に試す

Swagger UI で `/docs` にアクセスし、各エンドポイントの **「Try it out」** ボタンからパラメータを入力して実行できます。

## テスト実行

pytest で自動テストを実行します。認証の挙動（API キー無し → 401、キー有り → 200）や、入力値の検証をカバーしています。

```bash
pytest test_api.py -v
```

**期待される出力**

```
test_api.py::test_health PASSED                  [ 20%]
test_api.py::test_generate_copy_no_key PASSED    [ 40%]
test_api.py::test_generate_copy_wrong_key PASSED [ 60%]
test_api.py::test_extract_facts_no_key PASSED    [ 80%]
test_api.py::test_extract_facts_with_key PASSED  [100%]

============== 5 passed in X.XXs ==============
```

## ディレクトリ構成

```
apparel-copy-api/
├── api.py                 # FastAPI アプリケーション
├── apparel_copy_v4.py     # 生成ロジック（Claude API 呼び出し）
├── test_api.py            # pytest テストスイート
├── README.md              # このファイル
└── requirements.txt       # pip 依存パッケージ（オプション）
```

## ワークフロー例

### 受託業務での使用例

1. **クラウドワークス/ランサーズで案件受注**
2. **商品画像をアップロード**
   ```bash
   curl -X POST "http://localhost:8000/generate-copy" \
     -H "X-API-Key: $API_KEY" \
     -F "images=@image1.jpg" \
     -F "images=@image2.jpg" \
     -F "known_facts=素材: 麻100% / サイズ: S,M,L"
   ```
3. **返ってきた JSON を整形、CSV/JSON として納品**
4. **品質チェック**
   - `uncertain` 欄に項目があれば、ブランド/仕入れ元サイトで確認
   - `conflicts` があれば修正

## 設計上のポイント

### API キー認証

すべてのエンドポイント（`/generate-copy`, `/extract-facts`）は、リクエストヘッダ `X-API-Key` の検証が必須です。

```bash
-H "X-API-Key: $APP_API_KEY"
```

キー無しまたは間違いの場合は **401 Unauthorized** で拒否されます。`/` （ヘルスチェック）のみ認証不要です。

### エラーハンドリング

| ステータス | 説明 |
|----------|------|
| 200 | 成功 |
| 401 | API キーが正しくない、または未設定 |
| 422 | リクエスト形式が不正（画像なし、不正なパラメータなど） |
| 502 | Claude API 側のエラー（内容は detail に含まれる） |

## 本番環境への展開

このコードを Ubuntu サーバーや クラウドホスティング（AWS, Heroku等）へ展開する場合：

1. **環境変数を安全に管理** … API キーは `.env` ではなく環境変数で
2. **ポート・ドメインを設定** … `--port 8080` / リバースプロキシ（Nginx等）で HTTPS 化
3. **ログ記録を有効化** … 処理時間、エラーを監視
4. **レート制限を検討** … 過度な API 呼び出しを制限（オプション）

## ライセンス

このプロジェクトは個人利用・ポートフォリオ用です。商用利用は要相談。

## 作者

Takanori Ishizawa（ishiz）  
[Atlas AI Lab](https://ishizawa-invalid.tail26f5fa.ts.net/)
