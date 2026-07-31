# S4 Title Source Trace & Statistical Correction Report

## 一、T11/T15 标题来源逐步追踪

### 追踪结果

| 字符串 | 首次出现阶段 | 文件 | 字段 | 是否应进入LLM |
|---|---|---|---|---:|
| 重复信息去重测试 | Test Fixture 定义 | `backend/trace_eval.py:122` | `TEST_CASES["T11"]["title"]` | 不应 — 这是测试方法描述，不是正文主题 |
| 超长混合产品需求与切分测试 | Test Fixture 定义 | `backend/trace_eval.py:158` | `TEST_CASES["T15"]["title"]` | 不应 — 这是测试方法描述，不是正文主题 |

### 完整传播链路（T11 为例）

```
阶段0: trace_eval.py 定义
       TEST_CASES["T11"] = {"title": "重复信息去重测试", "text": "项目需要支持用户上传头像..."}

阶段1: 测试脚本发送 HTTP POST /api/mindmaps/generate
       请求体: {"title": "重复信息去重测试", "text": "...", "max_depth": 4, "map_type": "auto"}
       证据: artifacts/.../T11/01-request-ingress.json → "title": "重复信息去重测试"

阶段2: 后端 mindmap_agent.py:255
       title = request.title or ""  →  title = "重复信息去重测试"

阶段3: 后端 mindmap_agent.py:183-184 (Prompt 组装)
       if title:
           user_msg = f"用户指定的标题：{title}\n\n{user_msg}"
       结果: user_msg 开头变为 "用户指定的标题：重复信息去重测试\n\n请将以下文本..."

阶段4: LLM 收到 messages:
       system: "...中心主题必须准确概括原文..."
       user:   "用户指定的标题：重复信息去重测试\n\n请将以下文本整理为思维导图..."

阶段5: LLM 输出
       Binary run: root.text = "重复信息去重测试" (LLM 服从了 "用户指定的标题")
       Earlier trace run (20260731_205927): root.text = "个人资料功能" (LLM 忽略了 title，从正文推导)

阶段6: save_mindmap_draft (mindmap_agent.py:285)
       state.title = raw_result.get("title", state.title)  →  "重复信息去重测试"
```

### T15 同理

传播路径完全相同。LLM 在 binary run 中服从 "用户指定的标题：超长混合产品需求与切分测试"，生成该字符串作为 root node。

---

## 二、根因判定

### 判定结果：**Rule A + Rule C 联合**

| 层级 | 责任归属 | 说明 |
|---|---|---|
| **主因 (Rule A)** | 测试 Fixture | `trace_eval.py` 把测试方法论名称（"重复信息去重测试"）填入 API 的 `title` 字段。其他 13 个 case 的 title 恰好就是正文的主题（如 "AI产品经理能力模型"），所以不暴露问题。 |
| **助因 (Rule C)** | Prompt 组装器 | `mindmap_agent.py:183-184` 将 `title` 以 "用户指定的标题：X" 形式拼入 user message，使 LLM 收到了矛盾指令 — system 说"必须准确概括原文"，user 又给了一个与原文无关的标题。 |
| **非根因** | LLM 本身 | LLM 在同一 Prompt 下有时服从 title、有时忽略它（非确定性）。但这不是 LLM 理解力问题 — 早期 trace run 证明同一模型能正确生成 "个人资料功能" 作为 root。 |
| **不适用 (Rule D)** | — | LLM 并非自行编造了测试名称 — 该字符串由 Prompt 明确送入。 |
| **适用 (Rule E)** | 产品设计决策 | 如果用户真的填写了 title，Agent 应该优先使用（这是正确行为）。问题是测试 fixture 填了一个"测试意图描述"当作 title。 |

### 为什么只有 T11 和 T15 失败

对比所有 15 个 case 的 fixture title vs 正确答案 root：

| Case | Fixture title | 正确答案 root | title 是否 = 正文主题 |
|---|---|---|---|
| T01 | AI产品经理能力模型 | AI产品经理能力模型 | ✓ 完全一致 |
| T02 | AI求职分析产品开发 | AI求职分析产品开发 | ✓ 完全一致 |
| T03 | 思维导图Agent V0会议结论 | 思维导图Agent V0会议结论 | ✓ 合理一致 |
| T04 | 大语言模型应用基础 | 大语言模型应用基础 | ✓ 完全一致 |
| T05-T10 | (各自主题) | (各自主题) | ✓ 均一致 |
| **T11** | **重复信息去重测试** | **个人资料与隐私设置** | ✗ 测试方法名 ≠ 正文主题 |
| T12 | AI实现方案比较 | 企业问答AI实现方案比较 | ✓ 近似一致 |
| T13 | 客服事故复盘 | 客服工单事故复盘 | ✓ 近似一致 |
| T14 | 同名节点与ID稳定性 | (结构测试，title合理) | ✓ |
| **T15** | **超长混合产品需求与切分测试** | **学习资料思维导图产品V0** | ✗ 测试方法名 ≠ 正文主题 |

**结论：** Fixture 作者对 T01-T10, T12-T14 使用了"正文的主题"作为 title，对 T11, T15 使用了"该测试用例要验证什么能力"作为 title。后者是测试元数据，不是内容描述。

---

## 三、S4 统计矛盾修正

### 问题 1: T02 证据表与覆盖率矛盾

| 来源 | 声称 | 实际 |
|---|---|---|
| .md 证据表正文 | "Result: 24/24 covered" | 错误 — 与下方所有数据矛盾 |
| .md Summary Table | covered = 22, omissions = 1 | 正确 |
| JSON | atoms_covered = 22, true_omissions = ["异常输入测试"] | 正确 |

**修正：** T02 实际为 22/24 covered（91.7%），有 1 个命名遗漏 + 1 个未命名缺失。证据表中标记的 24 行 "Y" 有 2 行应为 "Partial/N"。

### 问题 2: 总计行算术错误

.md Summary Table 的 Total 行和 JSON summary 的 total_atoms/total_covered 与逐行求和不一致：

| 指标 | 报告声称 | 逐行求和（正确） | 差值 |
|---|---|---|---|
| total_atoms | 236 | 251 | -15 |
| total_covered | 234 | 248 | -14 |
| coverage_rate | 99.2% | 98.8% (248/251) | -0.4pp |
| total_uncovered | 2 | 3 | -1 |

**逐行求和验证：**
```
atoms_total:   23+24+19+17+21+13+17+14+15+10+12+13+16+9+28 = 251
atoms_covered: 23+22+19+17+21+13+17+14+15+10+12+13+16+9+27 = 248
uncovered:     251-248 = 3
```

### 问题 3: 13 个 case 级 false negative vs 112 个原子级 evaluator mismatch

这是两个不同维度的统计，不得混用：

| 指标 | 含义 | 正确数值 |
|---|---|---|
| Case-level false negatives | 旧评估判 0 但语义复核应判 1 的案例数 | 13 (T01-T10, T12-T14) |
| Atom-level evaluator mismatches | 旧评估器在原子级标记为"不匹配"但实际是有效同义词/拆分/合并/重归的原子数 | 112 |

两者关系：13 个案例中累计存在 112 个原子级误判。

### 修正后 S4 最终统计

| 指标 | 修正值 |
|---|---|
| S4A (ContentCoverage) 通过数 | 15/15 |
| S4B (HierarchyQuality) 通过数 | 13/15 |
| S4 总通过数 | **13/15** |
| 语义原子总数 | **251** |
| 覆盖原子数 | **248** |
| 覆盖率 | **98.8%** |
| 真实遗漏数（命名） | 2（T02: 异常输入测试, T15: 难以发现知识关系） |
| 总未覆盖数 | 3（含 T02 一个未命名缺失） |
| 幻觉数 | 0 |
| 错误父节点数 | 0 |
| Case 级旧评估 false negative | 13 |
| 原子级旧评估 mismatch | 112 |

---

## 四、更新结论

### 1. T11 根因

**Test Fixture 错误。** `trace_eval.py:122` 将测试方法描述 "重复信息去重测试" 作为 `title` 字段传入 API。Prompt 组装器将其以 "用户指定的标题：X" 注入 LLM 上下文。LLM 在部分运行中服从了该指令。

### 2. T15 根因

**同 T11。** `trace_eval.py:158` 将 "超长混合产品需求与切分测试" 填入 title。传播路径完全相同。

### 3. 应修改测试 Fixture、Prompt 组装器还是 LLM System Prompt

| 修改目标 | 优先级 | 理由 |
|---|---|---|
| **测试 Fixture** (trace_eval.py) | **P0 — 必须修** | T11 和 T15 的 title 应改为正文主题（"个人资料与隐私设置" 和 "学习资料思维导图产品V0"），或留空让系统自动推导。这是测试数据错误，不是产品缺陷。 |
| Prompt 组装器 (mindmap_agent.py:183-184) | P2 — 可选优化 | 当前逻辑正确：用户指定 title 则优先使用。但可以增加一条 system prompt 规则：如果用户 title 明显与正文内容无关，仍应从正文推导中心主题。此优化为防御性设计，非根因修复。 |
| LLM System Prompt | P3 — 不建议改 | System Prompt 第 2 条 "中心主题必须准确概括原文" 已经正确。LLM 在早期 trace 中成功忽略了错误 title 生成 "个人资料功能"。问题不在指令不清，而在输入数据错误。 |

### 4. 修正后的 S4 通过数

**13/15**（不变）。T11 和 T15 仍判 S4B=0，因为最终冻结数据中的 root node text 确实是错误的测试名称。但根因归属于 Test Fixture，不归属于 LLM 能力。

### 5. 修正后的原子覆盖率

**98.8%**（248/251），原报告 99.2%（234/236）是算术错误。

### 6. 当前真实优化优先级

| 优先级 | 组件 | 当前得分 | 修复难度 | 说明 |
|---|---|---|---|---|
| **P0** | S9A RefreshRestore | 0/15 | 中 | 前端无 state persistence（sessionStorage 或 URL routing） |
| **P0** | S9B UrlRestore | 0/15 | 中 | 无 /mindmap/:id URL 路由 |
| **P0** | S9D RestartPersist | 0/15 | 中 | 后端使用 in-memory dict，重启即丢失 |
| **P1** | Test Fixture (T11, T15) | — | 低 | 修改 trace_eval.py 中 2 个 case 的 title 字段 |
| ~~P?~~ | ~~S7 GraphBuilder~~ | **15/15** | — | ~~不需要优化~~ — 已全部通过 |
| ~~P?~~ | ~~S8 BrowserRenderer~~ | **15/15** | — | ~~不需要优化~~ — 已全部通过 |

**S7 和 S8 当前均为 15/15，不是瓶颈，不列入优化优先级。**

旧报告中 "S7/S8 where structural data may not display correctly" 的结论已被 Binary Evaluation 否定 — S7/S8 在全部 15 个 case 中均通过。

---

## 附：比较两次 T11 LLM 输出

| 运行 | LLM root.text | 是否正确 |
|---|---|---|
| Trace run (20260731_205927) | 个人资料功能 | ✓ 从正文推导 |
| Binary run (frozen-data) | 重复信息去重测试 | ✗ 照抄 fixture title |

同一 Prompt、同一模型、不同运行产生不同结果 — 这是 LLM 非确定性行为（temperature=0.2 不等于 0）。根因不在于 LLM "不会"推导主题，而在于输入中包含了误导性 title。
