# Отчёт о покрытии шаблонами: бурение (Басарыгин, §4.1.1 и §4.2.14)

Доменный пакет `domain/drilling` собран командой `python run.py domain-bootstrap drilling --from-chapter basarygin` за **1,6 мин** (96 с), ручных правок 0.
Движок не менялся. Узлов: 19.

## Сводка
- Иллюстрации курса: шаблоны по типам трудности сработали на всех 19 узлах без изменений (схемы из утверждений узла).
- Форматы по маршрутизации: шортс — 3, практикум на данных — 12, интерактив — 3, длинное видео — 1.
- Шаблоны сцен по типам: tpl_signal_response_property — 4, tpl_feature_cards — 2, tpl_procedure_flow — 5, tpl_decision_range — 2, tpl_formula_sliders — 1, tpl_mechanism_chain — 4, tpl_section_views — 1.
- Ролик: шаблон well_tool_curve (ствол, прибор/долото, кривая из модели пласта) подходит к узлам про приток в ствол; для объёма раствора в приёмной ёмкости и схемы обвязки устья нужен новый шаблон сцены — это доменное расширение, не правка движка.

## По узлам
| Узел | Тип трудности | Формат | Шаблон сцены | Подошёл без изменений |
|---|---|---|---|---|
| Как приток виден на поверхности (basarygin.signs_overview) | И | шортс | tpl_signal_response_property | да, ролик по шаблону well_tool_curve |
| Скачок проходки как ранний сигнал (basarygin.rop_jump) | Р/Н | практикум на данных | tpl_feature_cards | да (схема курса) |
| Чувствительность контроля уровня раствора (basarygin.level_resolution) | И/Ф | практикум на данных | tpl_signal_response_property | да (схема курса) |
| Как не потерять приток в шуме ёмкостей (basarygin.level_practice) | Пр/Н | интерактив | tpl_procedure_flow | да (схема курса) |
| Расход на выходе: порог и подача насоса (basarygin.flow_out) | И/Ф | практикум на данных | tpl_signal_response_property | да (схема курса) |
| Откуда газ в растворе (basarygin.gas_causes_signs) | Р/М | практикум на данных | tpl_feature_cards | да (схема курса) |
| Что делать при росте газа (basarygin.gas_actions) | Н/Пр | практикум на данных | tpl_decision_range | да (схема курса) |
| Расчёт газа и почему он не причина выброса (basarygin.gas_formulas) | Ф/М | практикум на данных | tpl_formula_sliders | да (схема курса) |
| Давление на насосах: падает или растёт (basarygin.pump_pressure) | М/Ф | практикум на данных | tpl_mechanism_chain | да (схема курса) |
| Баланс долива и вытеснения при СПО (basarygin.trips_volumes) | Пр/И | практикум на данных | tpl_procedure_flow | да (схема курса) |
| Свойства раствора как слабый сигнал (basarygin.mud_properties) | И/Н | практикум на данных | tpl_signal_response_property | да (схема курса) |
| Приток при избыточном давлении: не опасен (basarygin.causes_intro) | М | шортс | tpl_mechanism_chain | частично: нужен шаблон «ёмкость и устье» |
| Зачем усиливают устье газовой скважины (basarygin.wellhead_strengthening) | М | шортс | tpl_mechanism_chain | частично: нужен шаблон «ёмкость и устье» |
| Устройство обвязки устья: позиции схемы (basarygin.wellhead_layout) | П/Пр | интерактив | tpl_section_views | да (схема курса) |
| Закрытая скважина: приток затухает (basarygin.closing_physics) | М/Ф | длинное видео | tpl_mechanism_chain | частично: нужен шаблон «ёмкость и устье» |
| Первые действия и быстрое закрытие (basarygin.closing_prep_hard) | Пр/Н | интерактив | tpl_procedure_flow | да (схема курса) |
| Мягкое закрытие и выбор способа (basarygin.closing_soft_choice) | Н/Пр | практикум на данных | tpl_decision_range | да (схема курса) |
| Метод бурильщика: два этапа глушения (basarygin.killing_driller) | Пр/Ф | практикум на данных | tpl_procedure_flow | да (схема курса) |
| Глушение за один цикл (basarygin.killing_wait_weight) | Пр/Н | практикум на данных | tpl_procedure_flow | да (схема курса) |
