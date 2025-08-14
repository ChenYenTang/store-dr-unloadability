
# Store DR Unloadability

以歷史與即時資料估算各冷藏/冷凍櫃「可安全卸載時間」與「卸載優先順序」。本專案提供：
- **FastAPI**：`/api/v1/evaluate`、`/health`、`/version`
- **Gradio 介面**：掛載於 **/ui**，可上傳/檢核 `config.yaml`、建立櫃別與溫度映射、建立 JSON 並一鍵打 API。

## 快速開始

```bash
pip install -r requirements.txt

# 啟動 API + UI（/ui）
uvicorn src.main:app --host 0.0.0.0 --port 8000

# 瀏覽
# API:   http://localhost:8000/api/v1/health
# UI:    http://localhost:8000/ui
```

> 預設設定檔放在 `config/config.yaml`，也可用環境變數 `CONFIG_PATH` 指定路徑。

## API（/api/v1）
- `POST /evaluate`：依傳入各櫃即時溫度與狀態，回傳 `unloadable_time_min / unloadable_energy_kWh / priority_score` 與排序。
- `GET  /health`：健康檢查。
- `GET  /version`：版本資訊。

### Evaluate 範例
```bash
curl -s http://localhost:8000/api/v1/evaluate -H "Content-Type: application/json" -d @examples/payload.json | jq .
```

## 設計說明
- **演算法**：此版本提供「保守估計版」：用 `threshold - current_value` 的剩餘溫差 ÷ `rise_c_per_min_max` 推估關機下到達門檻的時間，再依 `defrost.grace_min / penalty_factor` 進行縮減，僅做範例。實戰請替換為你們的灰箱熱模型 + LSTM 斜率校正。
- **優先分**：依 `weights` 將時間與能量標準化計分，加上風險與除霜懲罰。

## 專案結構
```
src/
  api/routes.py         # FastAPI 路由與 /evaluate
  io/schema.py          # Pydantic 請求/回應 Models
  policy/config_loader.py
  policy/scoring.py
  ui/gradio_app.py      # Gradio 介面，掛在 /ui
  main.py               # 啟動點：Mount UI + API
config/config.yaml      # 預設設定
examples/payload.json   # 範例請求
```
