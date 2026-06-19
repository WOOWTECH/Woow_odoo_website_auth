# Task Plan: HA Dashboard — 前台网站 Home Assistant 数据仪表板

## Goal
使用 WoOW Snippet Builder 模块的 4 种 snippet（Stat Card、Chart、Data Table、Dynamic Content）在 Odoo 前台网站建立一个综合的 Home Assistant 数据仪表板页面，展示设备、实体、历史数据和区域分布。

## Current Phase
All phases complete

## Phases

### Phase 1: 白名单扩展 — 让 HA 模型可用
- [ ] 在 woow_snippet_builder 的 controller 中扩展 `_get_allowed_models()` 添加 HA 模型
- [ ] 目标模型: ha.device, ha.entity, ha.entity.history, ha.area, ha.label, ha.instance, ha.entity.group
- [ ] 部署到容器并验证 `/woow_snippet/available_models` 返回 HA 模型
- **Status:** pending

### Phase 2: 建立 HA Dashboard 前台页面
- [ ] 创建新的网站页面模板 `/ha-dashboard`
- [ ] 设计页面布局：顶部统计区 → 图表区 → 设备表格 → 实体表格
- [ ] 使用现有 snippet 模板结构 (section > container > snippet)
- **Status:** pending

### Phase 3: 统计卡片区 — 设备/实体总览 KPI
- [ ] 设备总数 (ha.device count)
- [ ] 实体总数 (ha.entity count)
- [ ] 区域总数 (ha.area count)
- [ ] 历史记录总数 (ha.entity.history count)
- [ ] 配置 data-* 属性指向正确的 HA 模型
- **Status:** pending

### Phase 4: 图表区 — 分布与趋势
- [ ] 按区域的设备分布 (Bar Chart, group_by: area_id)
- [ ] 按 domain 的实体分布 (Pie Chart, group_by: domain)
- [ ] 按制造商的设备分布 (Bar Chart, group_by: manufacturer)
- [ ] 实体历史趋势 (Line Chart, ha.entity.history, label: last_changed, value: num_state)
- **Status:** pending

### Phase 5: 数据表格区 — 设备与实体列表
- [ ] 设备列表 (ha.device): name, manufacturer, model, area_id, sw_version
- [ ] 实体列表 (ha.entity): entity_id, name, domain, entity_state, area_id, last_changed
- [ ] 配置搜索、排序、分页功能
- **Status:** pending

### Phase 6: 部署与验证
- [ ] 部署到容器 (podman cp + module upgrade)
- [ ] 截图验证所有区域正确渲染
- [ ] 运行评测确认 97+ 测试通过
- [ ] Commit & Push
- **Status:** pending

## Key Questions
1. HA 模型字段是否需要特殊处理？(many2one 字段如 area_id 在聚合时可能需要注意)
2. ha.entity.history 的 num_state 字段是否有足够数据来画趋势图？
3. 是否需要新建 controller 继承还是直接修改现有 controller？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 直接扩展现有 controller 的白名单 | 模块内修改最简单，无需新建继承模块 |
| 使用纯 snippet 拼装方式建页面 | 复用现有 4 种 snippet，无需写新 JS/Python |
| 页面 URL 为 /ha-dashboard | 清晰的路径命名 |
| HA 模型白名单: 7 个核心模型 | 覆盖 device/entity/history/area/label/instance/group |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |

## Notes
- 容器 bind mount 在 a19f 工作树，任何文件修改需要 podman cp 到容器
- Odoo 静态文件有 7 天缓存 (Cache-Control: max-age=604800)
- 数据库名: odoo-websitesnippet，用户: odoo-websitesnippet
