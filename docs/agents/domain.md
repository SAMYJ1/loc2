# Domain docs

## 阅读顺序

探索代码或修改领域行为前：
1. 阅读仓库根目录的 GLOSSARY.md。
2. 阅读 docs/adr/ 下与当前任务相关的 ADR。
3. 涉及应用需求时阅读 docs/usb-app-design.md；
   涉及实测能力时同时阅读 docs/validation-baseline.md。

文档缺失时继续工作；确有术语或决策需要记录时，
再通过 domain-modeling 工作流补充。

## 布局

本仓库采用 single-context：
- GLOSSARY.md：统一领域术语。
- docs/adr/：架构决策。

## 使用规则

Issue、规格、代码和测试使用术语表中的定义。
尤其区分选点草稿、应用目标位置、报点、位置采用、
停止报点和恢复真实位置。

发现术语缺口时明确指出，供 domain-modeling 处理。
方案与已有 ADR 冲突时，指出具体 ADR 和冲突原因，
明确提出是否重新讨论该决策。

已确认的产品目标与已完成的真机验证分别表述。
