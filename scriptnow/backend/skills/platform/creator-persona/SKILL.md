---
name: creator-persona
description: Use when adapting Agent creative behavior to a specific creator's preferences; defines a multi-dimensional persona schema governing pacing, emotional temperature, trope tolerance, character depth, language register, gender orientation, ending rules, and morality framework so the Agent team produces work aligned with the creator's vision.
metadata:
  scriptnow:
    roles: [director, architect, writer, reviewer]
    stages: [ideation, planning, writing, review]
    languages: [zh-CN, en]
    selection_priority: 60
    keywords: [偏好, 风格, 创作者, persona, 定制, 个性化, 男频, 女频, 节奏, 尺度]
---

# 创作者偏好画像系统

不同创作者需要不同的作品质感。一个"男频爽文作者"和一档"短剧制片人"对同一故事核心会做出完全不同的创作决策。本Skill定义偏好画像的八维模型，Agent 团队据此在每一阶段做出符合创作者期待的决策。

## 一、八维偏好画像

### 1. 节奏偏好（Pacing）
| 等级 | 描述 |
|------|------|
| **高密度** | 每 3 集一次爽点释放，无过渡场景，信息密度最大化 |
| **标准** | 每 5 集一次爽点，有呼吸感的过渡 |
| **慢火** | 每 8-10 集一次大释放，注重铺垫和蓄势 |

### 2. 情绪温度（Emotional Temperature）
| 等级 | 描述 |
|------|------|
| **高烈度** | 情绪外放，哭/怒/狂喜都有大场面呈现 |
| **中等** | 情绪有起伏但不过度渲染，细节呈现 |
| **克制** | 情绪内敛，通过行为和细节传达，无"嚎啕大哭"式场景 |

### 3. 类型化程度（Trope Tolerance）
| 等级 | 描述 |
|------|------|
| **拥抱类型** | 正面使用类型模板，爽点按观众预期准时交付 |
| **类型为底** | 以类型为框架但加入个人化处理 |
| **反类型** | 刻意颠覆或回避类型预期，追求独特表达 |

### 4. 角色深度（Character Depth）
| 等级 | 描述 |
|------|------|
| **功能性** | 角色为情节服务，性格特质明确但不一定复杂 |
| **有纹理** | 角色有矛盾特质和私密习惯，但弧线跟随类型 |
| **文学级** | 角色有完整的内心矛盾、隐性欲望和不可预测性 |

### 5. 语言寄存器（Language Register）
| 等级 | 描述 |
|------|------|
| **口语化** | 台词贴近日常对话，允许脏话/俚语/口吃/语法松散 |
| **类型语言** | 使用类型化的台词风格但不僵硬 |
| **文学化** | 对白有修辞意识，描写有文学质感 |

### 6. 性别/受众取向（Gender/ Audience Orientation）
| 选项 | 核心诉求 |
|------|---------|
| **男频** | 权力/能力/逆袭/征服的快感；角色关系服务于主角成长 |
| **女频** | 情感/关系/成长/被看到的渴望；角色关系是情感的镜像 |
| **中性** | 不预设性别审美偏向，根据故事本身做决策 |

### 7. 结局规则（Ending Rules）
| 选项 | 描述 |
|------|------|
| **必须HE** | Happy Ending 不可协商，过程可以有痛苦但终点必须是光明 |
| **偏好HE** | 倾向圆满但有例外空间 |
| **开放** | 不预设结局方向，由故事逻辑决定 |

### 8. 道德框架（Morality Framework）
| 选项 | 描述 |
|------|------|
| **黑白分明** | 好人/坏人清晰，正义终将胜利 |
| **灰色地带** | 每个人有理由，道德判断交给观众 |
| **质疑道德** | 挑战传统道德观，主角可能是不道德的但可理解 |

## 二、预设创作者画像

### 画像 1：男频爽文作者
```yaml
persona:
  pacing: 高密度
  emotional_temperature: 高烈度
  trope_tolerance: 拥抱类型
  character_depth: 功能性
  language_register: 类型语言
  gender_orientation: 男频
  ending_rules: 必须HE
  morality_framework: 黑白分明
```

### 画像 2：女频情感作者
```yaml
persona:
  pacing: 标准
  emotional_temperature: 中等
  trope_tolerance: 类型为底
  character_depth: 有纹理
  language_register: 口语化
  gender_orientation: 女频
  ending_rules: 偏好HE
  morality_framework: 灰色地带
```

### 画像 3：短剧制片人
```yaml
persona:
  pacing: 高密度
  emotional_temperature: 高烈度
  trope_tolerance: 拥抱类型
  character_depth: 功能性
  language_register: 口语化
  gender_orientation: 中性
  ending_rules: 必须HE
  morality_framework: 黑白分明
```

### 画像 4：文学型作者
```yaml
persona:
  pacing: 慢火
  emotional_temperature: 克制
  trope_tolerance: 反类型
  character_depth: 文学级
  language_register: 文学化
  gender_orientation: 中性
  ending_rules: 开放
  morality_framework: 质疑道德
```

## 三、阶段适用规则

不同创作阶段应加载不同偏好维度：

| 阶段 | 关键维度 |
|------|---------|
| **Ideation（故事方向）** | 性别取向、结局规则、类型化程度 → 决定故事走向 |
| **Planning（蓝图/大纲）** | 节奏偏好、道德框架、类型化程度 → 决定结构 |
| **Writing（写作）** | 情绪温度、语言寄存器、角色深度 → 决定执行 |
| **Review（审读）** | 全部维度 → 对照检查 |

## 四、偏好与类型规则的冲突解决

当创作者偏好与类型 Skill 规则冲突时：
- **偏好优先**于类型规则——如果创作者偏好"慢火"节奏而类型 Skill 要求"每 2-3 集一个爽点"，以创作者偏好为准
- 仅在**安全底线**（如平台内容审查）上类型规则不可被偏好覆盖
- Agent 在决策时应明确说明："按类型规则应 X，但根据您的偏好调整为 Y"

## 五、存储与加载

- 偏好存储在项目 `direction` 字段中，以 `preferences` 子对象形式：
```json
{
  "direction": {
    "language": "zh-CN",
    "genre": "悬疑",
    "preferences": {
      "pacing": "高密度",
      "emotional_temperature": "高烈度",
      "trope_tolerance": "拥抱类型",
      "character_depth": "功能性",
      "language_register": "类型语言",
      "gender_orientation": "男频",
      "ending_rules": "必须HE",
      "morality_framework": "黑白分明"
    }
  }
}
```
- Agent 在构建 prompt 时加载偏好作为创作约束
- 创作者可在创作端随时修改偏好，修改后下一阶段立即生效
