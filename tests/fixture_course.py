"""Сборка курса на синтетическом слое без модели: проверка сборщика и схем."""
import copy, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from g2k.chapter import load_chapter
from g2k import course, illus, route_tasks as RT, domain as D
from g2k.quotes import PageIndex
from g2k.layer import finalize_node
cfg = json.load(open(ROOT / 'chapters.json', encoding='utf8'))
ch = load_chapter('latyshova', cfg['latyshova'], ROOT); dom = D.load('geo'); pi = PageIndex(ch.pages)
n = json.load(open(ROOT / 'schemas/example_layer.json', encoding='utf8'))['nodes'][0]
n['claims'][0]['id'] = 'c1'
n['course'] = {"novice_title": "Когда по виду кривых не понять", "essence": ["В смешанном разрезе коллектор выделяют только расчётом.", "Качественных признаков не хватает."],
 "explain": [{"text": "Разные сочетания породы и флюида дают похожие отклики приборов.", "claims": ["c1"]}],
 "procedure": [{"text": "Собрать комплекс ГИС", "claims": ["c1"]}, {"text": "Посчитать параметры", "claims": ["c1"]}, {"text": "Сопоставить с геологией", "claims": ["c1"]}],
 "numbers": [], "formulas": [{"tex": "\rho_п = P_п \rho_в", "meaning": "сопротивление пласта", "vars": [{"sym": "\rho_п", "meaning": "сопротивление пласта", "unit": "Ом·м"}], "claims": ["c1"]}],
 "glossary": [{"term": "коллектор", "en": "reservoir", "definition": "порода, способная вмещать и отдавать флюид", "claims": ["c1"]}], "tables": [{"unit_id": "p091.03", "title": "таблица"}], "figures": []}
n['video_scores'] = {"time": 0, "invisible": 2, "scale": 0, "counterintuitive": 2, "cause_effect": 1}
node = finalize_node(n, {"id": n['id'], "units": [], "difficulty": n['difficulty']}, 1, ch, pi)
n2 = json.loads(json.dumps(node).replace(node['id'], 'latyshova.second')); n2['difficulty'] = {'primary': 'Пр', 'secondary': None}
n2['links'] = [{"type": "prerequisite", "target": node['id']}]
layer = {"chapter": ch.chapter_id, "source": ch.md, "nodes": [node, n2]}
c1 = node['claims'][0]['id']; s1 = "step." + node['id']
tasks = {"chapter": ch.chapter_id, "tasks": [
 {"id": "t1", "type": "single", "step_id": s1, "claim_ids": [c1], "prompt": "Как выделяют коллектор в смешанном разрезе?", "options": [{"id": "a", "text": "По виду кривой"}, {"id": "b", "text": "Количественной интерпретацией"}, {"id": "c", "text": "По керну только"}], "answer": "b", "explanation": "Так сказано в главе."},
 {"id": "t2", "type": "order", "step_id": s1, "claim_ids": [c1], "prompt": "Расставьте шаги", "options": [{"id": "a", "text": "Собрать комплекс"}, {"id": "b", "text": "Посчитать"}, {"id": "c", "text": "Сопоставить"}], "answer": ["a", "b", "c"], "explanation": "Порядок процедуры."},
 {"id": "t3", "type": "gap", "step_id": s1, "claim_ids": [c1], "prompt": "Коллектор выделяют {{1}} интерпретацией.", "options": [], "answer": ["количественной"], "explanation": "..."},
 {"id": "t4", "type": "calc", "step_id": s1, "claim_ids": [c1], "prompt": "Посчитайте $\rho_п$ при $P_п=10$ и $\rho_в=0.1$", "options": [], "answer": 1.0, "tolerance": 0.05, "unit": "Ом·м", "explanation": "10×0.1"},
 {"id": "t5", "type": "multiple", "step_id": "step.latyshova.second", "claim_ids": [n2['claims'][0]['id']], "prompt": "Что верно?", "options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}, {"id": "c", "text": "z"}, {"id": "d", "text": "w"}], "answer": ["a", "b"], "explanation": "..."}]}
routing = RT.route(layer)
out = ROOT / 'out/_fixture'; ills = illus.build(layer, dom['style'], out / 'course' / 'assets')
p = course.build(ch, layer, tasks, routing, ills, out / 'course')
print(p, p.stat().st_size)
