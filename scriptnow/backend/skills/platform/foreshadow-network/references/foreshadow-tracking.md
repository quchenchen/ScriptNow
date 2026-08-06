# 伏笔追踪表示例

以下为 Agent 在编写过程中应维护的伏笔追踪表格式。每次布设新伏笔或回收已有伏笔后更新。

## 追踪表字段

| 字段 | 说明 |
|------|------|
| id | 唯一标识，格式：FSH-XXX |
| type | 物件/对话/行为/身份 |
| plant_unit | 布设位置（集/章编号） |
| plant_form | 布设形式（对话中的一句话/物件出现/角色动作） |
| surface_meaning | 表面含义（读者当时的理解） |
| hidden_meaning | 隐藏含义（回收时揭示的真相） |
| signal_unit | 暗示位置（可多个） |
| payoff_unit | 预计回收位置 |
| status | planted / signaled / payoff-ready / resolved / overdue |
| resolved_unit | 实际回收位置（回收后填写） |
| chain_effect | 回收后产生的连锁影响 |

## 示例追踪记录

```json
{
  "id": "FSH-001",
  "type": "物件",
  "plant_unit": "第3集",
  "plant_form": "主角母亲遗物中的一张褪色照片，背面有模糊字迹",
  "surface_meaning": "母亲年轻时的照片",
  "hidden_meaning": "照片中的第三人被裁剪掉了——那个人的手还搭在母亲肩上",
  "signal_unit": ["第7集（主角翻看时停顿了一下）", "第12集（照片在关键时刻滑出钱包）"],
  "payoff_unit": "第18集",
  "status": "resolved",
  "resolved_unit": "第18集",
  "chain_effect": "主角确认母亲当年的背叛不是自愿，复仇目标从个人恩怨转向揭露组织"
}
```

## 密度检查规则

- 同一集中大伏笔（身份类）布设不超过 1 个
- 同一集中物件伏笔不超过 2 个
- 超过预计回收位置 5 集仍未回收的伏笔标记为 overdue，优先级最高
- 布设后 3 集内必须有至少一次暗示提及（哪怕只是物件在背景中出现）
