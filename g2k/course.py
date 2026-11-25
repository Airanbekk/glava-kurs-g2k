"""Шаг 4. Демо-курс: один самодостаточный HTML-файл из учебного слоя (без сервера и логина)."""
from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KATEX = ROOT / "tools" / "node_modules" / "katex" / "dist"


def _katex_inline() -> tuple[str, str]:
    if not (KATEX / "katex.min.js").exists():
        return "", ""
    css = (KATEX / "katex.min.css").read_text(encoding="utf-8")

    def font(m):
        f = KATEX / "fonts" / m.group(1)
        return f"url(data:font/woff2;base64,{base64.b64encode(f.read_bytes()).decode()}) format(\"woff2\")"
    css = re.sub(r"url\(fonts/([^)]+?\.woff2)\) format\(\"woff2\"\)", font, css)
    css = re.sub(r",\s*url\(fonts/[^)]+?\.(woff|ttf)\) format\(\"(woff|truetype)\"\)", "", css)
    js = (KATEX / "katex.min.js").read_text(encoding="utf-8")
    return css, js


def md_table_to_html(text: str) -> str:
    rows = [r.strip() for r in text.strip().splitlines() if r.strip().startswith("|")]
    if not rows:
        return f"<pre>{html.escape(text)}</pre>"
    out = ["<div class='tbl'><table>"]
    first = True
    for r in rows:
        cells = [c.strip() for c in r.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        tag = "th" if first else "td"
        out.append("<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>")
        first = False
    out.append("</table></div>")
    return "".join(out)


def _parts(nodes: list[dict]) -> list[dict]:
    """Части курса: группы по 3–5 шагов по порядку графа."""
    n = len(nodes)
    k = max(1, round(n / 4))
    size = -(-n // k)
    return [{"title": f"Часть {i + 1}", "steps": [x["id"] for x in nodes[i * size:(i + 1) * size]]} for i in range(k)]


def build(chapter, layer: dict, tasks: dict, routing: dict, ills: dict, out_dir: Path, media: dict | None = None,
          book_title: str = "") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {}
    for n in layer["nodes"]:
        for t in (n.get("course") or {}).get("tables") or []:
            u = chapter.unit(t.get("unit_id", ""))
            if u is not None:
                tables[t["unit_id"]] = {"html": md_table_to_html(u.text), "page": u.page, "title": t.get("title", "")}
    svgs = {}
    for il in ills["illustrations"]:
        p = out_dir / il["file"]
        if p.exists() and p.suffix == ".svg":
            svgs[il["id"]] = p.read_text(encoding="utf-8")
    data = {
        "chapter": layer["chapter"], "book": book_title or chapter.book, "nodes": layer["nodes"],
        "parts": _parts(layer["nodes"]), "tasks": tasks["tasks"], "routes": routing["routes"],
        "ills": ills["illustrations"], "svgs": svgs, "tables": tables, "media": media or {},
    }
    css_k, js_k = _katex_inline()
    page = TEMPLATE.replace("/*KATEX_CSS*/", css_k).replace("/*KATEX_JS*/", js_k.replace("</script", "<\\/script"))
    page = page.replace("__TITLE__", html.escape(data["book"]))
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = page.replace("/*DATA*/", blob)
    out = out_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — демо-курс</title>
<style>/*KATEX_CSS*/</style>
<style>
:root{--bg:#f7f8fa;--panel:#fff;--text:#14181d;--muted:#5b6672;--line:#dde2e8;--acc:#b7791f;--accbg:#fff6e0;--ok:#1e7f4f;--okbg:#e4f5ec;--bad:#b42318;--badbg:#fdecea;--model:#6b46c1;--modelbg:#f1ecfb;--link:#0b62c4;color-scheme:light}
:root[data-theme=dark]{--bg:#0f1419;--panel:#1a2129;--text:#eceff4;--muted:#a3adb8;--line:#2c3640;--acc:#f1c40f;--accbg:#2a2614;--ok:#4cd08a;--okbg:#12291e;--bad:#ff7b72;--badbg:#2d1414;--model:#b39dfa;--modelbg:#221a35;--link:#79b8ff;color-scheme:dark}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1419;--panel:#1a2129;--text:#eceff4;--muted:#a3adb8;--line:#2c3640;--acc:#f1c40f;--accbg:#2a2614;--ok:#4cd08a;--okbg:#12291e;--bad:#ff7b72;--badbg:#2d1414;--model:#b39dfa;--modelbg:#221a35;--link:#79b8ff;color-scheme:dark}}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--text);font:17px/1.6 "Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;overflow-x:hidden}
a{color:var(--link)}button,input,select{font:inherit;color:inherit}
:focus-visible{outline:3px solid var(--acc);outline-offset:2px;border-radius:6px}
header{position:sticky;top:0;z-index:5;background:var(--panel);border-bottom:1px solid var(--line)}
.hwrap{max-width:980px;margin:0 auto;padding:10px 16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.brand{font-weight:700;font-size:16px;flex:1;min-width:180px;line-height:1.3}
.brand small{display:block;color:var(--muted);font-weight:400;font-size:14px}
nav{display:flex;gap:6px;flex-wrap:wrap}
nav button,.btn{border:1px solid var(--line);background:var(--panel);border-radius:10px;padding:8px 12px;cursor:pointer;min-height:44px}
nav button[aria-current=true]{background:var(--accbg);border-color:var(--acc)}
.btn.primary{background:var(--acc);border-color:var(--acc);color:#111;font-weight:600}
.prog{height:6px;background:var(--line)}.prog>i{display:block;height:100%;background:var(--acc);width:0;transition:width .3s}
main{max-width:980px;margin:0 auto;padding:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:28px;line-height:1.25;margin:6px 0}h2{font-size:21px;margin:22px 0 8px}h3{font-size:18px;margin:14px 0 6px}
.book{color:var(--muted);font-size:15px}
.pill{display:inline-block;font-size:13px;padding:1px 8px;border-radius:999px;border:1px solid var(--line);color:var(--muted);white-space:nowrap;margin-left:4px;cursor:pointer;background:none}
.pill.model{color:var(--model);border-color:var(--model);background:var(--modelbg);cursor:default}
.essence{background:var(--accbg);border-left:5px solid var(--acc);padding:12px 16px;border-radius:10px}
.essence p:first-child{font-weight:600}
.hyp{background:var(--modelbg);border-left:4px solid var(--model);padding:8px 12px;border-radius:8px;margin:8px 0}
.mist{background:var(--badbg);border-left:4px solid var(--bad);padding:10px 14px;border-radius:8px}
.steps-list{list-style:none;padding:0;margin:0}
.steps-list li{display:flex;gap:10px;align-items:center;padding:10px 4px;border-bottom:1px solid var(--line)}
.steps-list li button{flex:1;text-align:left;border:none;background:none;cursor:pointer;padding:4px;min-height:44px}
.done{color:var(--ok);font-weight:700;width:22px}
.meta{color:var(--muted);font-size:14px}
.tbl{overflow-x:auto}table{border-collapse:collapse;min-width:100%;font-size:15px}td,th{border:1px solid var(--line);padding:6px 8px;text-align:left}
figure{margin:12px 0}figure svg,figure img,figure video{width:100%;height:auto;border-radius:12px;display:block}
figcaption{color:var(--muted);font-size:14px;margin-top:6px}
details{border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:8px 0}summary{cursor:pointer;font-weight:600;min-height:32px}
blockquote{margin:6px 0;padding:6px 12px;border-left:3px solid var(--line);color:var(--muted);font-size:15px}
.task{border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
.task .q{font-weight:600}.opt{display:flex;gap:10px;align-items:flex-start;padding:8px;border-radius:10px;border:1px solid var(--line);margin:6px 0;cursor:pointer;min-height:44px}
.opt input{width:20px;height:20px;margin-top:3px}
.order li{list-style:none;display:flex;gap:8px;align-items:center;padding:10px;margin:6px 0;border:1px solid var(--line);border-radius:10px;background:var(--panel);touch-action:none;user-select:none;cursor:grab}
.order{padding:0}.order li.drag{opacity:.6;border-color:var(--acc)}.order .h{font-size:20px;color:var(--muted)}.order li span{flex:1}
.order li button{min-width:40px;min-height:40px;border:1px solid var(--line);border-radius:8px;background:none}
input.gap,input.num{border:1px solid var(--line);border-radius:8px;padding:6px 8px;background:var(--bg);min-width:110px;max-width:100%}
.fb{margin-top:10px;padding:10px 12px;border-radius:10px}.fb.ok{background:var(--okbg);color:var(--ok)}.fb.no{background:var(--badbg);color:var(--bad)}
.fb .exp{color:var(--text)}
.nav2{display:flex;justify-content:space-between;gap:10px;margin:20px 0}
.flash{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.fc{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;min-height:180px;display:flex;flex-direction:column}
.fc .front{font-weight:700;font-size:18px}.fc .back{margin-top:8px;flex:1}.fc .row{display:flex;gap:8px;margin-top:10px}
.fc.known{border-color:var(--ok)}.fc.again{border-color:var(--bad)}
.katex-display{overflow-x:auto;overflow-y:hidden;padding:4px 0}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:14px;color:var(--muted)}
.mapwrap{overflow-x:auto}
@media (max-width:600px){h1{font-size:23px}main{padding:10px}.card{padding:14px}html,body{font-size:16px}}
@media print{header,.nav2,.noprint,nav{display:none!important}.card{border:none;break-inside:avoid}body{background:#fff;color:#000}}
</style>
</head>
<body>
<a href="#main" class="pill" style="position:absolute;left:-999px" onfocus="this.style.left='8px'">К содержимому</a>
<header><div class="hwrap">
<div class="brand" id="brand"></div>
<nav aria-label="Разделы">
<button data-v="path">Путь</button><button data-v="cards">Карточки</button><button data-v="notes">Конспект</button><button data-v="map">Карта</button>
<button id="theme" aria-label="Сменить тему">◐</button>
</nav></div><div class="prog" aria-hidden="true"><i id="bar"></i></div></header>
<main id="main" tabindex="-1"></main>
<script>/*KATEX_JS*/</script>
<script>
const D=/*DATA*/;
const $=s=>document.querySelector(s), E=(t,a={},...c)=>{const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==='html')e.innerHTML=v;else if(k.startsWith('on'))e.addEventListener(k.slice(2),v);else e.setAttribute(k,v)}for(const x of c.flat(Infinity)){if(x==null)continue;e.append(x.nodeType?x:document.createTextNode(x))}return e};
const KEY='g2k:'+D.chapter; let S={}; try{S=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
S.done=S.done||{};S.cards=S.cards||{};S.tasks=S.tasks||{};
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}};
const nodes=D.nodes, byId=Object.fromEntries(nodes.map(n=>[n.id,n]));
const claimById={};nodes.forEach(n=>(n.claims||[]).forEach(c=>claimById[c.id]=c));
const tasksBy={};D.tasks.forEach(t=>{(tasksBy[t.step_id]=tasksBy[t.step_id]||[]).push(t)});
const illBy={};D.ills.forEach(i=>{(illBy[i.step_id]=illBy[i.step_id]||[]).push(i)});
const routeBy=Object.fromEntries(D.routes.map(r=>[r.node_id,r]));
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function tex(s,disp){try{return window.katex?katex.renderToString(s,{displayMode:!!disp,throwOnError:false}):esc(s)}catch(e){return esc(s)}}
function inlineTex(s){return esc(s).replace(/\$([^$]{1,80})\$/g,(m,x)=>tex(x.replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&')))}
function pages(ids){const ps=[...new Set((ids||[]).map(i=>claimById[i]&&claimById[i].page_pdf).filter(Boolean))].sort((a,b)=>a-b);return ps}
function srcPill(ids){const ps=pages(ids);if(!ps.length)return E('span',{class:'pill model',title:'Нет опоры на утверждение главы'},'пояснение модели');
 return E('button',{class:'pill',title:'Показать цитату автора','aria-label':'Источник: стр. '+ps.join(', '),onclick:()=>showQuote(ids)},'стр. '+ps.join(', '))}
function modelPill(f){return f&&f.by_model?E('span',{class:'pill model',title:'Поле написано моделью, а не взято из книги'},f.hypothesis?'гипотеза модели':'пояснение модели'):null}
function showQuote(ids){const d=E('dialog',{style:'max-width:640px;border-radius:14px;border:1px solid var(--line);background:var(--panel);color:var(--text)'});
 d.append(E('h3',{},'Опора в главе'),...ids.map(i=>claimById[i]).filter(Boolean).map(c=>E('div',{},E('p',{},c.text,' ',E('b',{},'стр. '+c.page_pdf)),E('blockquote',{},'«'+c.quote+'»'))),E('button',{class:'btn',onclick:()=>d.close()},'Закрыть'));
 document.body.append(d);d.showModal();d.addEventListener('close',()=>d.remove())}
function stepTime(n){const c=n.course||{};const w=JSON.stringify(c).split(/\s+/).length;return Math.max(3,Math.round(w/170+(tasksBy['step.'+n.id]||[]).length))}
function progress(){const k=nodes.filter(n=>S.done[n.id]).length;$('#bar').style.width=(100*k/nodes.length)+'%';return k}
function setView(v,arg){document.querySelectorAll('nav [data-v]').forEach(b=>b.setAttribute('aria-current',b.dataset.v===v));
 S.view=v;if(arg)S.step=arg;save();const m=$('#main');m.innerHTML='';({path,step,cards,notes,map})[v](m,arg);m.focus({preventScroll:true});window.scrollTo(0,0);progress()}
$('#brand').append(D.book,E('small',{},'Демо-курс по главе · собран конвейером из учебного слоя'));
document.querySelectorAll('nav [data-v]').forEach(b=>b.onclick=()=>setView(b.dataset.v));
$('#theme').onclick=()=>{const r=document.documentElement;const cur=r.dataset.theme||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');r.dataset.theme=cur==='dark'?'light':'dark';S.theme=r.dataset.theme;save()};
if(S.theme)document.documentElement.dataset.theme=S.theme;

function path(m){const k=progress();
 m.append(E('div',{class:'card'},E('h1',{},'Путь по главе'),E('p',{class:'book'},D.book),
  E('p',{},`Шагов: ${nodes.length} · пройдено: ${k} · заданий: ${D.tasks.length}`),
  S.step&&byId[S.step]?E('button',{class:'btn primary',onclick:()=>setView('step',S.step)},'Продолжить с места: '+((byId[S.step].course||{}).novice_title||byId[S.step].title)):
  E('button',{class:'btn primary',onclick:()=>setView('step',nodes[0].id)},'Начать'),
  E('p',{class:'legend'},E('span',{},'стр. N — ссылка на страницу книги'),E('span',{class:'pill model'},'пояснение модели'),E('span',{},'— написано моделью, не автором'))));
 D.parts.forEach(p=>{m.append(E('div',{class:'card'},E('h2',{},p.title),E('ol',{class:'steps-list'},p.steps.map((id,i)=>{const n=byId[id];const r=routeBy[id]||{};
  return E('li',{},E('span',{class:'done','aria-label':S.done[id]?'пройдено':'не пройдено'},S.done[id]?'✓':'·'),E('button',{onclick:()=>setView('step',id)},E('div',{},(n.course||{}).novice_title||n.title),E('div',{class:'meta'},`${n.title} · ~${stepTime(n)} мин · ${r.format||''}`)))}))))})}

function section(title,...kids){kids=kids.flat(Infinity).filter(Boolean);return kids.length?[E('h2',{},title),...kids]:[]}
function step(m,id){const n=byId[id]||nodes[0];const c=n.course||{};const L=n.layers||{};const i=nodes.indexOf(n);
 const card=E('article',{class:'card'});
 card.append(E('div',{class:'meta'},`Шаг ${i+1} из ${nodes.length} · ~${stepTime(n)} мин · тип трудности ${n.difficulty.primary}${n.difficulty.secondary?'/'+n.difficulty.secondary:''}`),
  E('h1',{},c.novice_title||n.title),E('p',{class:'book'},'В книге: «'+n.title+'» · стр. '+(n.pages||[]).join(', ')));
 card.append(E('div',{class:'essence'},...(c.essence||[]).map(s=>E('p',{style:'margin:4px 0'},s))));
 (illBy['step.'+n.id]||[]).forEach(il=>card.append(E('figure',{},E('div',{role:'img','aria-label':il.alt,html:D.svgs[il.id]||''}),E('figcaption',{},il.caption+' · '+il.source))));
 const md=D.media[n.id];if(md)card.append(E('h2',{},'Ролик'),E('figure',{},E('video',{controls:'',preload:'metadata',src:md.src,'aria-label':md.title},E('track',{kind:'subtitles',src:md.vtt||'',srclang:'ru',label:'Русские',default:''})),E('figcaption',{},md.title)));
 card.append(...section('Как это работает',(c.explain||[]).map(p=>E('p',{},p.text,' ',srcPill(p.claims)))));
 card.append(...section('По шагам',(c.procedure||[]).length?E('ol',{},(c.procedure||[]).map(p=>E('li',{},p.text,' ',srcPill(p.claims)))):null));
 card.append(...section('Разбор примеров из главы',(n.worked_examples||[]).map((w,k)=>E('details',{open:''},E('summary',{},`Пример ${k+1} · стр. ${w.page_pdf}`),E('p',{},E('b',{},'Условие. '),w.condition),E('ol',{},(w.steps||[]).map(s=>E('li',{},s))),E('p',{},E('b',{},'Итог. '),w.result),w.figure?E('p',{class:'meta'},'Рисунок: '+w.figure):null))));
 card.append(...section('Цифры и условия',(c.numbers||[]).length?E('ul',{},(c.numbers||[]).map(p=>E('li',{},p.text,' ',srcPill(p.claims)))):null));
 const fl=(c.formulas||[]).map(f=>E('div',{},E('div',{html:tex(f.tex,1)}),E('p',{},f.meaning,' ',srcPill(f.claims)),(f.vars||[]).length?E('ul',{},(f.vars||[]).map(v=>E('li',{},E('span',{html:tex(v.sym)}),' — '+v.meaning+(v.unit?', '+v.unit:'')))):null));
 const gl=(c.glossary||[]).length?E('dl',{},(c.glossary||[]).map(g=>[E('dt',{},E('b',{},g.term),g.en?E('span',{class:'meta'},' · '+g.en):''),E('dd',{},g.definition,' ',srcPill(g.claims))])):null;
 card.append(...section('Понятия и формулы',gl,fl));
 card.append(...section('Таблицы книги',(c.tables||[]).map(t=>D.tables[t.unit_id]?E('figure',{},E('div',{html:D.tables[t.unit_id].html}),E('figcaption',{},`${t.title} · стр. ${D.tables[t.unit_id].page} · перенесено из текста главы без правок; ошибки распознавания не исправлялись`)):null)));
 if(n.misconception)card.append(...section('Частая ошибка',E('div',{class:'mist'},n.misconception.text,' ',modelPill(n.misconception))));
 const dm=n.data_meaning||{};card.append(...section('Что это значит для данных',dm.from_chapter?E('p',{},dm.from_chapter.text,' ',modelPill(dm.from_chapter)):null,dm.breaks?E('p',{},E('b',{},'Где ломается: '),dm.breaks.text,' ',modelPill(dm.breaks)):null,(dm.hypotheses||[]).map(h=>E('div',{class:'hyp'},E('b',{},'Гипотеза: '),h.text)),
  n.decision_on_data?E('div',{class:'hyp'},E('b',{},'Решение на данных. '),'Признаки: '+(n.decision_on_data.features||[]).join('; ')+'. Правило: '+n.decision_on_data.rule+'. Вывод: '+n.decision_on_data.conclusion+(n.decision_on_data.counterexample?'. Контрпример: '+n.decision_on_data.counterexample:'')):null));
 if(n.it_analogy)card.append(...section('Аналогия из ИТ',E('p',{},n.it_analogy.text,' ',modelPill(n.it_analogy)),E('p',{},E('b',{},'Где аналогия не работает: '),n.it_analogy.breaks_where)));
 if(L.nuances&&L.nuances.text)card.append(...section('Нюансы',E('p',{},L.nuances.text,' ',modelPill(L.nuances))));
 if(n.now_practice)card.append(...section('Как это делают сейчас',E('p',{},n.now_practice.text,' ',modelPill(n.now_practice))));
 card.append(...section('Задачи из книги',(n.book_tasks||[]).map(t=>E('p',{},E('b',{},`Задача ${t.number} (стр. ${t.page_pdf}). `),t.text,t.figure?E('span',{class:'meta'},' · нужен '+t.figure):''))));
 card.append(E('details',{},E('summary',{},`Источники шага: ${(n.claims||[]).length} утверждений с цитатами автора`),...(n.claims||[]).map(cl=>E('div',{},E('p',{style:'margin:8px 0 2px'},cl.text,' ',E('b',{},'стр. '+cl.page_pdf),' ',E('span',{class:'meta'},({observation:'наблюдение',inference:'вывод',assumption:'допущение'})[cl.kind]||'')),E('blockquote',{},'«'+cl.quote+'»')))));
 const ts=tasksBy['step.'+n.id]||[];if(ts.length){card.append(E('h2',{},'Задания'));ts.forEach(t=>card.append(taskEl(t)))}
 card.append(E('div',{class:'nav2'},i>0?E('button',{class:'btn',onclick:()=>setView('step',nodes[i-1].id)},'← Назад'):E('span'),
  E('button',{class:'btn primary',onclick:()=>{S.done[n.id]=1;save();i<nodes.length-1?setView('step',nodes[i+1].id):setView('path')}},i<nodes.length-1?'Готово, дальше →':'Завершить главу ✓')));
 m.append(card)}

function shuffle(a,seed){a=a.slice();let s=[...seed].reduce((x,c)=>x*31+c.charCodeAt(0)>>>0,7);for(let i=a.length-1;i>0;i--){s=(s*1103515245+12345)>>>0;const j=s%(i+1);[a[i],a[j]]=[a[j],a[i]]}return a}
function taskEl(t){const box=E('div',{class:'task'});const kindRu={single:'один ответ',multiple:'несколько ответов',order:'порядок',gap:'пропуски',calc:'расчёт'}[t.type];
 box.append(E('div',{class:'meta'},kindRu));let get;
 if(t.type==='gap'){const p=E('p',{class:'q'});const parts=t.prompt.split(/\{\{(\d+)\}\}/);const ins=[];
  parts.forEach((s,k)=>{if(k%2===0)p.append(s);else{const inp=E('input',{class:'gap','aria-label':'Пропуск '+s});ins.push(inp);p.append(inp)}});box.append(p);get=()=>ins.map(x=>x.value.trim())}
 else box.append(E('p',{class:'q',html:inlineTex(t.prompt)}));
 if(t.type==='single'||t.type==='multiple'){const nm='n'+t.id;const opts=t.options.map(o=>E('label',{class:'opt'},E('input',{type:t.type==='single'?'radio':'checkbox',name:nm,value:o.id}),E('span',{html:inlineTex(o.text)})));box.append(...opts);
  get=()=>{const v=[...box.querySelectorAll('input:checked')].map(x=>x.value);return t.type==='single'?v[0]:v}}
 if(t.type==='order'){const ul=E('ul',{class:'order','aria-label':'Перетащите или используйте стрелки'});const items=shuffle(t.options,t.id);
  const mk=o=>{const li=E('li',{'data-id':o.id},E('span',{class:'h','aria-hidden':'true'},'⠿'),E('span',{},o.text),E('button',{'aria-label':'Выше',onclick:()=>{li.previousElementSibling&&ul.insertBefore(li,li.previousElementSibling)}},'↑'),E('button',{'aria-label':'Ниже',onclick:()=>{li.nextElementSibling&&ul.insertBefore(li.nextElementSibling,li)}},'↓'));
   li.addEventListener('pointerdown',e=>{if(e.target.tagName==='BUTTON')return;li.setPointerCapture(e.pointerId);li.classList.add('drag');
    const mv=ev=>{const sib=[...ul.children].filter(x=>x!==li);const after=sib.find(x=>{const r=x.getBoundingClientRect();return ev.clientY<r.top+r.height/2});after?ul.insertBefore(li,after):ul.append(li)};
    const up=()=>{li.classList.remove('drag');li.removeEventListener('pointermove',mv);li.removeEventListener('pointerup',up)};li.addEventListener('pointermove',mv);li.addEventListener('pointerup',up)});return li};
  items.forEach(o=>ul.append(mk(o)));box.append(ul);get=()=>[...ul.children].map(x=>x.dataset.id)}
 if(t.type==='calc'){const inp=E('input',{class:'num',inputmode:'decimal','aria-label':'Ответ'});box.append(E('p',{},inp,' ',t.unit||''));get=()=>inp.value}
 const fb=E('div',{class:'fb',role:'status','aria-live':'polite',hidden:''});
 box.append(E('button',{class:'btn primary',onclick:()=>{const v=get();const ok=check(t,v);S.tasks[t.id]=ok?1:0;save();fb.hidden=false;fb.className='fb '+(ok?'ok':'no');fb.innerHTML='';
  fb.append(E('b',{},ok?'Верно. ':'Неверно. '),E('div',{},'Правильный ответ: ',E('span',{html:inlineTex(answerText(t))})),E('div',{class:'exp'},t.explanation,' ',srcPill(t.claim_ids)))}},'Проверить'),fb);return box}
const nn=s=>String(s).toLowerCase().replace(/ё/g,'е').replace(/\s+/g,' ').trim();
function check(t,v){if(t.type==='single')return v===t.answer;if(t.type==='multiple'||t.type==='order'){const a=t.answer;return Array.isArray(v)&&(t.type==='order'?v.join()===a.join():v.slice().sort().join()===a.slice().sort().join())}
 if(t.type==='gap')return v.every((x,k)=>nn(x)===nn(t.answer[k]));if(t.type==='calc'){const x=parseFloat(String(v).replace(',','.')),a=parseFloat(String(t.answer).replace(',','.'));const tol=t.tolerance!=null?t.tolerance:Math.abs(a)*0.02;return Math.abs(x-a)<=tol+1e-9}return false}
function answerText(t){const o=Object.fromEntries((t.options||[]).map(x=>[x.id,x.text]));if(t.type==='single')return o[t.answer]||t.answer;if(t.type==='multiple')return t.answer.map(a=>o[a]).join('; ');if(t.type==='order')return t.answer.map((a,k)=>(k+1)+') '+o[a]).join(' ');if(t.type==='gap')return t.answer.join(', ');return t.answer+(t.unit?' '+t.unit:'')}

function cards(m){m.append(E('div',{class:'card'},E('h1',{},'Карточки'),E('p',{class:'meta'},'Карточки по всем узлам. Отмечайте «знаю» или «повторить»: отметки сохраняются в браузере.'),
 E('div',{class:'noprint'},E('button',{class:'btn',onclick:()=>{const g=$('.flash');[...g.children].forEach(x=>x.hidden=S.cards[x.dataset.id]==='k');}},'Показать только «повторить»'),' ',E('button',{class:'btn',onclick:()=>setView('cards')},'Все'))));
 const g=E('div',{class:'flash'});nodes.forEach(n=>{const c=n.course||{};const st=S.cards[n.id];const back=E('div',{class:'back',hidden:''},(c.essence||[]).join(' '));
  const el=E('div',{class:'fc'+(st==='k'?' known':st==='r'?' again':''),'data-id':n.id},E('div',{class:'front'},c.novice_title||n.title),E('div',{class:'meta'},'Вспомните суть, затем откройте'),back,
   E('div',{class:'row'},E('button',{class:'btn',onclick:()=>back.hidden=!back.hidden},'Открыть'),E('button',{class:'btn',onclick:()=>{S.cards[n.id]='k';save();el.className='fc known'}},'Знаю'),E('button',{class:'btn',onclick:()=>{S.cards[n.id]='r';save();el.className='fc again'}},'Повторить')));g.append(el)});m.append(g)}

function notes(m){m.append(E('div',{class:'card'},E('h1',{},'Конспект главы'),E('p',{class:'book'},D.book),E('button',{class:'btn primary noprint',onclick:()=>print()},'Печать / сохранить в PDF')));
 nodes.forEach((n,i)=>{const c=n.course||{};m.append(E('section',{class:'card'},E('h2',{},`${i+1}. ${c.novice_title||n.title}`),E('p',{class:'book'},'«'+n.title+'», стр. '+(n.pages||[]).join(', ')),
  ...(c.essence||[]).map(s=>E('p',{},s)),(c.numbers||[]).length?E('ul',{},(c.numbers||[]).map(p=>E('li',{},p.text+' (стр. '+pages(p.claims).join(', ')+')'))):null,
  ...(c.formulas||[]).map(f=>E('div',{html:tex(f.tex,1)})),n.misconception?E('p',{class:'mist'},'Частая ошибка: '+n.misconception.text):null))})}

function map(m){const depth={};nodes.forEach(n=>{const pre=(n.links||[]).filter(l=>l.type==='prerequisite'&&byId[l.target]&&nodes.indexOf(byId[l.target])<nodes.indexOf(n)).map(l=>depth[l.target]??0);depth[n.id]=pre.length?Math.max(...pre)+1:0});
 const cols={};nodes.forEach(n=>(cols[depth[n.id]]=cols[depth[n.id]]||[]).push(n));const nc=Object.keys(cols).length;const W=Math.max(360,nc*230),rows=Math.max(...Object.values(cols).map(c=>c.length));const H=rows*92+40;
 const pos={};Object.entries(cols).forEach(([d,arr])=>arr.forEach((n,k)=>pos[n.id]=[20+d*230,20+k*92]));
 let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" style="max-width:none" role="img" aria-label="Карта связей шагов"><defs><marker id="m" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0L10,5L0,10z" fill="currentColor"/></marker></defs>`;
 nodes.forEach(n=>(n.links||[]).forEach(l=>{if(!pos[l.target]||!['prerequisite','example_of'].includes(l.type))return;const[a,b]=pos[l.target],[c,d]=pos[n.id];s+=`<path d="M${a+200},${b+34} C${a+215},${b+34} ${c-15},${d+34} ${c},${d+34}" fill="none" stroke="currentColor" stroke-opacity=".45" stroke-width="2" ${l.type==='example_of'?'stroke-dasharray="5 4"':''} marker-end="url(#m)"/>`}));
 nodes.forEach((n,i)=>{const[x,y]=pos[n.id];const t=esc(((n.course||{}).novice_title||n.title));s+=`<g tabindex="0" role="link" data-id="${n.id}" style="cursor:pointer"><rect x="${x}" y="${y}" width="200" height="68" rx="12" fill="var(--panel)" stroke="${S.done[n.id]?'var(--ok)':'var(--line)'}" stroke-width="2"/><foreignObject x="${x+8}" y="${y+4}" width="186" height="62"><div xmlns="http://www.w3.org/1999/xhtml" style="font-size:13px;line-height:1.25">${i+1}. ${t}</div></foreignObject></g>`});
 s+='</svg>';const w=E('div',{class:'mapwrap',html:s});w.querySelectorAll('g[data-id]').forEach(g=>{g.onclick=()=>setView('step',g.dataset.id);g.onkeydown=e=>{if(e.key==='Enter')setView('step',g.dataset.id)}});
 m.append(E('div',{class:'card'},E('h1',{},'Карта связей шагов'),E('p',{class:'meta'},'Стрелка — предпосылка; пунктир — пример. Нажмите на шаг, чтобы открыть его.'),w))}

setView(S.view&&S.view!=='step'?S.view:(S.step?'step':'path'),S.view==='step'?S.step:undefined);
</script>
</body>
</html>"""
