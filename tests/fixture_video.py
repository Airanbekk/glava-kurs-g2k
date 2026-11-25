"""Ролик на ручной спецификации без модели: проверка рендера, озвучки и сборки MP4."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from g2k import video, domain as D
dom = D.load('geo')
node = json.load(open(ROOT / 'schemas/example_layer.json', encoding='utf8'))['nodes'][0]
cid = node['claims'][0]['id']
spec = {"title": "Высокое сопротивление — ещё не нефть", "hook": "?",
 "params": {"depth_top": 2000, "depth_bottom": 2024, "tool_resolution_m": 0.8,
   "curve": {"key": "RES", "label": "Сопротивление", "unit": "Ом·м", "min": 0, "max": 60},
   "layers": [{"top": 2000, "bottom": 2006, "lith": "shale", "fluid": None, "label": "глина", "value": 3},
              {"top": 2006, "bottom": 2012, "lith": "sand", "fluid": "oil", "label": "песчаник с нефтью", "value": 40},
              {"top": 2012, "bottom": 2017, "lith": "dense", "fluid": None, "label": "плотный известняк", "value": 50},
              {"top": 2017, "bottom": 2024, "lith": "sand", "fluid": "water", "label": "песчаник с водой", "value": 4}]},
 "beats": [{"say": "Кривая сопротивления поднялась. Значит, тут нефть?", "claim_id": cid, "on_screen": "Нефть?", "tool_depth": 2003},
           {"say": "Нефть не проводит ток, поэтому нефтяной пласт даёт высокое сопротивление.", "claim_id": cid, "on_screen": "Нефть", "tool_depth": 2010, "highlight": [2006, 2012]},
           {"say": "Но плотный известняк без пор тоже почти не проводит ток.", "claim_id": cid, "on_screen": "Плотная порода", "tool_depth": 2015, "highlight": [2012, 2017]},
           {"say": "Вода с солями проводит ток, и сопротивление падает.", "claim_id": cid, "on_screen": "Вода", "tool_depth": 2022}],
 "exaggerations": ["ширина ствола увеличена примерно в двадцать раз"], "prediction_question": "?", "transfer_question": "?", "data_it_bridge": "-"}
video.make_spec = lambda node, dom, aspect: spec
for asp in ("9:16", "16:9"):
    r = video.build({"nodes": [node]}, {"routes": [{"node_id": node['id'], "format": "шортс", "video_scores": {"a": 1}}]}, dom, ROOT / 'out/_fixture/media', aspect=asp, node_id=node['id'])
    print(r['passport']['audio_check'])
