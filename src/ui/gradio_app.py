
import os, json
import httpx
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import gradio as gr
import pandas as pd

from src.io.schema import EvaluateRequest, CabinetInput

DEFAULT_CONFIG_YAML = """
thresholds:
  refrigerator:
    air_return_c_max: 7.0
    milk_surface_c_max: 6.0
    chill_mw_surface_c_max: 8.0
    rise_c_per_min_max: 0.5
  freezer:
    air_return_c_max: -15.0
    mw_freeze_surface_c_max: -12.0
    rise_c_per_min_max: 0.4
defrost:
  grace_min: 5
  penalty_factor: 0.8
weights:
  w_time: 0.35
  w_energy: 0.25
  w_risk: 0.20
  w_open: 0.05
  w_dload: 0.10
  w_defrost: 0.05
""".strip()

CABINET_COLUMNS = [
    "cabinet_id","type","air_supply_c","air_return_c",
    "prod_t_mw_chill_c","prod_t_milk_c","prod_t_mw_freeze_c",
    "defrost_status","time_since_defrost_min",
]
CABINET_DTYPES = ["str","str","number","number","number","number","number","number","number"]

def _now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def load_yaml_from_file(file_obj) -> str:
    import yaml
    if file_obj is None: return DEFAULT_CONFIG_YAML
    try:
        with open(file_obj.name, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    except Exception as e:
        return f"# Failed to read YAML: {e}\n\n{DEFAULT_CONFIG_YAML}"

def validate_config_yaml(yaml_text: str):
    import yaml
    try:
        data = yaml.safe_load(yaml_text)
        assert "thresholds" in data and "defrost" in data and "weights" in data
        return {"ok": True, "message": "YAML OK"}
    except Exception as e:
        return {"ok": False, "message": f"Invalid YAML: {e}"}

def save_config_yaml(yaml_text: str) -> str:
    out_dir = os.environ.get("CONFIG_DIR", "config")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "config.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(yaml_text)
    return path

def gen_default_rows(num_ref: int, num_fz: int):
    rows = []
    for i in range(int(num_ref)):
        rows.append([f"R-{i+1:02d}", "refrigerator", None, None, None, None, None, 0, 0])
    for j in range(int(num_fz)):
        rows.append([f"F-{j+1:02d}", "freezer", None, None, None, None, None, 0, 0])
    return rows

def generate_table(num_ref: float, num_fz: float):
    return gen_default_rows(int(num_ref), int(num_fz))

def _coerce_float(v):
    if v is None: return None
    try:
        fv = float(v)
        if fv != fv: return None
        return fv
    except Exception:
        return None

def assemble_payload(df, store_id: str, business_flag: str, timestamp: str):
    cabinets = []
    if df is None:
        return gr.update(value=None), gr.update(value=None), "請先建立或填寫櫃別表格"
    for _, row in df.iterrows():
        if (str(row.get("cabinet_id")) == "nan") or (str(row.get("type")) == "nan"):
            continue
        cab = CabinetInput(
            cabinet_id=str(row.get("cabinet_id")),
            type=str(row.get("type")),
            air_supply_c=_coerce_float(row.get("air_supply_c")),
            air_return_c=_coerce_float(row.get("air_return_c")),
            prod_t_mw_chill_c=_coerce_float(row.get("prod_t_mw_chill_c")),
            prod_t_milk_c=_coerce_float(row.get("prod_t_milk_c")),
            prod_t_mw_freeze_c=_coerce_float(row.get("prod_t_mw_freeze_c")),
            defrost_status=int(row.get("defrost_status") or 0),
            time_since_defrost_min=int(row.get("time_since_defrost_min") or 0),
        )
        cabinets.append(cab.dict())
    if not timestamp.strip():
        timestamp = _now_iso()
    req = EvaluateRequest(
        store_id=store_id.strip() or "S001",
        timestamp=timestamp.strip(),
        business_hours_flag=int(business_flag),
        cabinets=cabinets,
    )
    payload = json.loads(req.json())
    out_path = os.path.abspath("payload.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload, out_path, "OK"

async def post_to_api(payload: Dict[str, Any], base_url: str, api_key: str = ""):
    if not payload:
        return {"ok": False, "message": "請先點「建立 JSON」"}
    base = base_url.rstrip("/")
    url = f"{base}/evaluate"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            try:
                return r.json()
            except Exception:
                return {"ok": True, "status_code": r.status_code, "text": r.text}
    except httpx.HTTPStatusError as he:
        return {"ok": False, "status_code": he.response.status_code, "text": he.response.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def build_demo() -> gr.Blocks:
    with gr.Blocks(title="Store DR Unloadability Console") as demo:
        gr.Markdown(
            "# 門市卸載評估控制台\n"
            "- 載入/檢核 `config.yaml`\n"
            "- 輸入櫃數與即時溫度 → 自動生成表格（可改欄位）\n"
            "- 一鍵產生 API 請求 JSON，並可直接呼叫 `/evaluate`"
        )
        with gr.Tabs():
            with gr.Tab("Config 設定"):
                with gr.Row():
                    cfg_file = gr.File(label="上傳 config.yaml", file_types=[".yaml", ".yml"])
                    cfg_text = gr.Textbox(label="config.yaml（可編輯）", value=DEFAULT_CONFIG_YAML, lines=22)
                with gr.Row():
                    btn_load = gr.Button("從檔案載入→文字框")
                    btn_validate = gr.Button("檢核 YAML")
                    btn_save = gr.Button("儲存到伺服器 ./config/config.yaml")
                cfg_result = gr.JSON(label="結果")
                btn_load.click(load_yaml_from_file, inputs=cfg_file, outputs=cfg_text)
                btn_validate.click(validate_config_yaml, inputs=cfg_text, outputs=cfg_result)
                btn_save.click(save_config_yaml, inputs=cfg_text, outputs=cfg_result)

            with gr.Tab("櫃別與溫度輸入"):
                with gr.Row():
                    num_ref = gr.Number(label="冷藏櫃數（台）", value=2, precision=0)
                    num_fz = gr.Number(label="冷凍櫃數（台）", value=1, precision=0)
                    btn_gen = gr.Button("產生/更新表格")
                df = gr.Dataframe(
                    headers=CABINET_COLUMNS, datatype=CABINET_DTYPES,
                    row_count=5, col_count=(len(CABINET_COLUMNS), "fixed"),
                    type="pandas", label="櫃別/型態/即時溫度與旗標（可編輯）",
                )
                btn_gen.click(generate_table, inputs=[num_ref, num_fz], outputs=df)

            with gr.Tab("建立 JSON 與送出"):
                with gr.Row():
                    store_id = gr.Textbox(label="Store ID", value="S001")
                    business_flag = gr.Dropdown(choices=["0","1"], value="1", label="營業中旗標 1/0")
                    timestamp = gr.Textbox(label="時間戳（ISO8601）", value=datetime.now().astimezone().isoformat(timespec="seconds"))
                with gr.Row():
                    btn_build = gr.Button("建立 JSON")
                    btn_call = gr.Button("送到 /evaluate API")
                with gr.Row():
                    payload_json = gr.JSON(label="請求預覽")
                with gr.Row():
                    payload_file = gr.File(label="下載 payload.json")
                with gr.Accordion("API 連線設定", open=False):
                    api_base = gr.Textbox(label="API Base URL", value="http://localhost:8000/api/v1")
                    api_key = gr.Textbox(label="API Key（選填）", type="password")
                    api_resp = gr.JSON(label="API 回應")
                status_pipe = gr.Textbox(visible=False)
                btn_build.click(assemble_payload, inputs=[df, store_id, business_flag, timestamp], outputs=[payload_json, payload_file, status_pipe])
                btn_call.click(post_to_api, inputs=[payload_json, api_base, api_key], outputs=api_resp)
    return demo

if __name__ == "__main__":
    demo = build_demo()
    demo.queue().launch(server_name="0.0.0.0", server_port=7860)
