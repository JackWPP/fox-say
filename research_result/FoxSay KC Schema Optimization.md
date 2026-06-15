# **FoxSay 项目知识组件 Schema 与学习科学理论契合度评估及优化方案研究报告**

## **1\. 知识组件的学术定义与理论源起**

在学习科学与智能辅导系统（ITS）的发展历程中，知识组件（Knowledge Component，简称 KC）作为自适应学习模型的核心基石，其定义经历了两十余年的演进。卡内基梅隆大学的 Kenneth R. Koedinger、Vincent Aleven 以及匹兹堡大学的 Kurt VanLehn 等人在该领域奠定了重要的理论基础1。  
根据匹兹堡科学学习中心（PSLC）及相关学者的工作，知识组件（KC）被学术界标准定义为：**学习者在完成特定任务或解决问题步骤时，单独或与其他认知结构结合使用的一种持久性的脑部心理结构或认知过程的描述**1。KC 是对日常教学中“概念”（Concept）、“原理”（Principle）、“事实”（Fact）和“技能”（Skill）等通俗术语的统一抽象，也是认知科学中“产生式规则”（Production Rule）、“错误概念”（Misconception）、“图式”（Schema）以及“认知面”（Facet）等术语的通用化概括1。  
在具体应用中，判断学习者是否“拥有”某个知识组件可以通过两种层级来观测1：

* **显性知识组件（Explicit KC）**：学习者能够用语言直接陈述该组件（例如陈述几何学原理“对顶角相等”）1。这通常对应于陈述性知识（Declarative Knowledge），通过阅读、讲解等方式习得1。  
* **隐性知识组件（Implicit KC）**：学习者无法直接陈述规则，但在面对具体问题情境时能够做出符合该规则的行为（例如在代数方程求解中自动应用某种消元步骤）1。这对应于程序性知识（Procedural Knowledge），通常必须通过反复的实践和即时反馈来内化1。

知识组件的本质在于将特定的情境特征映射到相应的认知或行为反应上（Feature-to-Response Mapping）1。一个知识组件被判定为“正确”，意味着其关联的所有特征都与做出该反应直接相关，且不包含任何无关特征1。如果在特征编码中包含无关特征或遗漏关键特征，就会构成“错误 KC”（即误解，Misconception）1。  
从智能辅导系统的行为特征来看，VanLehn 提出了经典的双环行为模型（Two-loop Behavior）3。外环（Outer Loop）在多分钟的任务或问题层面运行，负责选择和调度任务；内环（Inner Loop）则在步骤（Step）层面运行，负责对学生的每一个物理交互（如在界面上输入一个数值或请求提示）进行秒级的实时诊断与动态反馈3。在这套机制中，内环所观测到的每一个界面操作被称为“物理步骤”（Step），而在学生大脑内部发生的、无法直接观测的认知建构或应用事件被称为“学习事件”（Learning Event）3。知识组件正是连接物理步骤与心理学习事件的数学建模桥梁，它决定了系统如何在内环中跟踪学生的认知状态并更新自适应算法参数2。  
为了更好地厘清学术界在不同语境下对“知识”的界定，下表对比了哲学、传统教育学与认知科学/ITS 领域的定义差异：

| 评估维度 | 哲学体系 (Philosophy) | 传统教育学 (Education) | 认知科学与 ITS 领域 (Cognitive Science & ITS) |
| :---- | :---- | :---- | :---- |
| **定义的本质** | 合理的真实信念 (Justified True Belief)1 | 基础事实与陈述性信息 (对应布鲁姆分类法第一级)1 | 大脑硬件中存储的、决定行为的知识库与认知结构1 |
| **正确性要求** | 必须绝对正确，否则无法构成知识1 | 默认教授正确内容，通常不将错误归入知识范畴 | 涵盖“正确 KC”与“错误 KC（误解/偏差图式）”1 |
| **认知表达层** | 显性化、语言化的论证 | 课本陈述、定义与事实1 | 包含程序、整合图式、复杂推理策略和元认知技能1 |

## **2\. 主流知识组件建模方法的深度解构**

在当前智能教育与教育数据挖掘（EDM）领域，针对知识组件的建模方法主要经历了从静态映射到动态概率追踪、从单一维度关联到多维图谱推理的演进过程。

### **2.1 学习因子分析（Learning Factors Analysis, LFA）与加法因子模型（AFM）**

LFA 是一种将统计建模与启发式搜索相结合的方法，旨在自动优化和改进专家人工定义的 KC 模型（即题目/步骤到技能的映射）5。LFA 的底层核心是加法因子模型（Additive Factors Model, AFM），它作为项目反应理论（IRT）的扩展，引入了随练习机会增加而产生的能力增长项6。其基本形式设定学生 ![][image1] 在应用第 ![][image2] 个知识组件的第 ![][image3] 次练习机会（Opportunity）时，正确解决步骤 ![][image4] 的概率 ![][image5] 符合逻辑斯蒂分布6：  
![][image6]  
其中，![][image7] 代表学生 ![][image1] 的先验综合能力（Student Proficiency）6；![][image8] 代表第 ![][image2] 个知识组件的基础难度（Baseline Difficulty）6；![][image9] 代表该知识组件的学习率（Learning Rate），即每多一次练习该技能时，学生掌握概率的提升速率8；![][image3] 代表学生 ![][image1] 在该步骤之前应用知识组件 ![][image2] 的累积练习次数6；而 ![][image10] 是映射矩阵（Q 矩阵）中的元素，当步骤 ![][image4] 包含知识组件 ![][image2] 时 ![][image11]，否则为 ![][image12]8。LFA 通过启发式合并或拆分 Q 矩阵中的 KC 节点，以寻找使整体模型更具解释力且参数更精简的最佳拓扑6。

### **2.2 PSLC DataShop 数据建模规范**

作为全球最大的开放式教育数据仓库，卡内基梅隆大学的 DataShop 提供了一套基于真实行为日志评估 KC 模型效能的科学评测体系7。DataShop 通过对导入的交易级（Transaction-level）行为流水进行统计拟合，对比不同 KC 划分模型在赤池信息量准则（AIC）、贝叶斯信息量准则（BIC）以及交叉验证均方根误差（RMSE）上的表现6。DataShop 最核心的思想在于平衡模型的精确性（避免过度细化导致学习曲线在极少练习后便终止）与泛化度（避免过粗导致学习曲线出现不规则的起伏或起伏异常，即 Spike）10。  
从工程实现角度看，为了实现与 DataShop 的互操作，导出的行为流水必须遵循严格的数据字典与时间格式标准11。其核心要素包括：

* **Anon Student Id** 与 **Session Id**：分别唯一标识匿名学生与辅导会话11。  
* **Time** 与 **Problem Start Time**：必须采用标准的 ISO 8601 格式变体（如 yyyy-MM-dd HH:mm:ss.SSS），亚秒级高精度时间对测算学生的首步反应延迟（Latency）至关重要11。  
* **Level（level\_title）**：表达题目的多层级目录结构（如 Level (Unit) 为 “一元一次方程”）11。  
* **Step Name**、**Selection**、**Action**：用于细粒度刻画内环步骤中的用户界面事件11。  
* **KC（kc\_model\_name）** 与 **KC Category**：描述步骤映射的具体知识组件及其分类11。

在 DataShop 实际工程流水线中存在一个著名的 Excel 兼容陷阱11：在利用 Excel 打开 DataShop 的 tab-delimited 文件并直接保存时，Excel 会默认将高精度的亚秒级时间格式截断为无日期或无亚秒的非标准格式（如 mm:ss.0），导致时间信息发生不可逆的永久性损坏11。因此，学术界与工程界在处理此类数据时，通常必须强制通过 Excel 的“文本导入向导”（Text Import Wizard）将所有时间序列字段指定为 Text 格式进行安全查看，或完全在 Python/Pandas 等无损数据流中进行预处理11。

### **2.3 Q 矩阵（Q-matrix）认知诊断理论**

Q 矩阵作为认知诊断模型（CDMs）与知识追踪（KT）的测验蓝图，描述了显性的测验题目（或步骤）与隐性的潜认知属性（KCs）之间的多对多二元对应关系12。 以经典的确定性输入嘈杂“与”门（DINA）模型为例，该模型假定认知属性之间是不可代偿的联合关系（Conjunctive Relationship）13。这意味着要答对题目 ![][image4]，学生必须完全掌握该题目关联的所有知识组件13：  
![][image13]  
其中，![][image14] 表示学生是否掌握属性 ![][image2]13。如果 ![][image11] 且学生 ![][image15]，则其理想正确状态 ![][image16]13。实际观测中，还会引入失误概率（Slip, ![][image17]）与猜测概率（Guess, ![][image18]）来调整概率曲线15。由于专家手工定义的 Q 矩阵极易引入主观偏见（Subjective Misspecifications），严重削弱自适应诊断的有效性14，现代研究通常引入数据驱动的校准机制（如 QRAKT 和 HKLQC 算法），通过挖掘大量学生真实答题序列中的条件概率分布，对 Q 矩阵中的 0-1 二值映射进行连续概率或层级校准，以提高追踪精度14。

### **2.4 教育知识图谱（Educational Knowledge Graph, EKG）**

教育知识图谱是将实体知识库演进为自适应推理引擎的重要手段18。它通过构建“资源-概念”（Resource-Concept）异构图，建立微课视频、练习题、课件与底层概念节点的多维链接19。  
在 Coursera、edX 等大规模开放式在线课程（MOOCs）的工程实践中，由于注册用户量大、人均做题数低，学习流水数据面临着极度的稀疏性与不完整性（Data Sparsity）20。为了解决此工程瓶颈，两家 MOOCs 平台的工程博客与相关技术研究表明，团队采用了先进的两阶段图表征模型——HetGNN-KGAT20：

1. **第一阶段（HetGNN）**：利用异构图神经网络，通过随机游走采样与多模态特征（如视频文本、概念定义、习题参数）的注意力聚合（Attentive Aggregation），对图谱中缺失的隐含关联（Implicit Links）和节点属性进行预补全（Imputation），从而显著改善数据 Completeness20。  
2. **第二阶段（KGAT）**：在补全后的丰富图谱上，运行知识图谱注意力网络（KGAT），通过基于注意力的信息传播（Attention-based Propagation）捕获高阶协同信号（High-order Collaborative Signals）与多步跨度依赖，从而在数据极度稀疏的背景下，为学习者输出极具 pedagogical 合理性的个性化课程与习题推荐20。

为了对比这四种主流的建模体系，下表总结了它们的技术栈和应用场景：

| 建模方法 | 输入数据要求 | 核心数学/算法模型 | 典型输出与应用 | 解决的关键局限性 |
| :---- | :---- | :---- | :---- | :---- |
| **LFA / AFM** | 学生练习步骤流水账、多套专家备选 Q 矩阵5 | 逻辑斯蒂回归 (AFM 混合效应模型)8 | 预测学习曲线、识别过度练习或缺乏练习的 KCs6 | 避免人工定义 KC 模型时的过度细化或粗糙化10 |
| **DataShop** | 符合标准 DTD 的事务级 XML/TSV 数据流11 | 极大似然估计、交叉验证 RMSE 评估6 | 可视化学习曲线、多 KC 模型效能横向对比6 | 提供统一的学术界评测基准，避免评估主观性10 |
| **Q-matrix** | 测验得分矩阵、属性关联矩阵12 | 潜类分析、DINA 模型、QRAKT / HKLQC 校准算法13 | 诊断个体学生的细粒度认知漏洞14 | 解决传统单维 IRT 只能估算综合能力、无法诊断具体技能的缺点15 |
| **EKG** | 概念集、资源文本、课本课件18 | 异构图神经网络 (HetGNN)、注意力图谱 (KGAT)20 | 动态自适应导航、冷启动概念链接补全18 | 克服 MOOC 平台及高利害备考中真实行为日志极度稀疏的瓶颈20 |

## **3\. 布鲁姆认知层级（Bloom's Taxonomy）的补完评估**

FoxSay 项目现有的认知水平分类采用简化版的 4 档（Remembering、Understanding、Applying、Analyzing）。在经典的布鲁姆分类法 2001 修订版中，认知层级由低到高由 6 档构成（Remember、Understand、Apply、Analyze、Evaluate、Create）24。系统是否需要引入顶层的 Evaluating（评价）与 Creating（创造），必须从认知发展理论与自适应系统工程两个层面进行利弊评估24。

### **3.1 补充 Evaluating 与 Creating 的学术利弊分析**

从正面效益来看，首先，**大语言模型（GenAI）时代重塑了认知金字塔的价值**26。当前生成式人工智能技术能够直接、高效地替代人类完成 Remembering、Understanding 甚至大部分 Applying 层次的任务27。如果系统的认知图谱止步于 Analyzing 层次，将无法有效评价学生在人机协同环境下进行方案辨析、信息校验（Evaluating）及原创方案构想（Creating）的批判性思维与高阶认知能力，极易导致教学场景的落后27。 其次，**引入高阶层级能避免自适应追踪的“天花板效应”**29。在面向高能力学生（例如知识追踪中掌握概率 ![][image19] 的群体）时，如果系统缺失 Evaluating 与 Creating 级别的 KC 节点，就无法为其推送具有高认知负荷的复杂探究任务，从而导致自适应推送引擎失去高能力段的分流控制精度29。 最后，**它极大地扩展了非数理学科的建模契合度**26。人文、语言、社会科学以及项目式学习（PBL）场景天然包含大量的 Evaluating（如评论一篇文章的逻辑漏洞）与 Creating（如撰写一篇具有新颖立意的议论文）30。  
然而，从工程与运营成本来看，补充这两个层级也面临着显著挑战。 第一，**ITS 内环评估的瓶颈限制**3。在智能辅导系统中，Evaluating 和 Creating 属于典型的开放式任务，其答案往往是非结构化的，极难定义客观一致的“特征-反应映射”1，这使得传统 ITS 很难在秒级内环（Inner Loop）中给出精准的自动化对错诊断与反馈3。 第二，**知识追踪中的参数稀疏问题**16。增加两个高阶认知维度意味着题目映射矩阵（Q 矩阵）的列数增加，在日常练习数据中，高阶题目的样本量天然稀少，这将导致知识追踪（BKT / DKT）模型中高阶 KC 的参数出现严重的过拟合与估计不准现象15。  
因此，更具合理性的系统策略应当是：**补全 6 阶分类法，但对顶层两级采用特异性的评估与交互机制**25。对于 Remembering 到 Analyzing 的 KCs，系统主要运行传统的基于 AFM/BKT 的内环练习反馈3；而对于 Evaluating 与 Creating 级的 KCs，则主要通过引入大语言模型作为智能同伴（如 Khan Academy 的 Khanmigo 系列机制），采用开放式苏格拉底对话（Self-explanation Dialogues）或“同伴纠错审计”等新型交互模式进行间接测定2。  
下表详细展示了修订版布鲁姆分类法在 FoxSay 系统中的落地行为映射及教学设计：

| 认知层级 | 知识加工本质 | 典型自适应干预策略 (Pedagogical Intervention) | 系统物理交互与测验设计 (Assessment Action) |
| :---- | :---- | :---- | :---- |
| **Remembering** | 识别并从长时记忆中检索特定事实30 | 动态自适应闪卡（Flashcards）、定义微课视频31 | 术语单选、概念连线、词汇填空30 |
| **Understanding** | 解释、分类、总结并建立概念间关联30 | 提供类比案例、要求生成自我解释（Self-explain）31 | 给出错误解法并要求判断是否合理、概念图归类25 |
| **Applying** | 在具体情境中执行某种固定的步骤24 | 分解式样例展示（Worked Examples）、单步提示25 | 套用公式计算数值、执行单步规范程序25 |
| **Analyzing** | 拆解结构、厘清要素间的逻辑关系24 | 提供复杂综合题的解题策略路径分解树31 | 多步骤几何证明、科学实验变量因果链分析31 |
| **Evaluating** | 基于特定的标准和规范进行评判24 | 错因审计、同伴互评（Peer Evaluation）工作流31 | 检查 AI 给出的一段解答过程，指出其中的隐藏漏洞并写出评语32 |
| **Creating** | 将要素重新整合，构建一个原创的功能整体24 | 科学探索沙盒环境、跨主题建模引导31 | 针对现实问题设计一套可行的软硬件架构或实验方案30 |

## **4\. Prerequisites 字段的设计模型与工业界实践**

先修关系（Dependency）在知识图谱与自适应引擎中扮演着“学习路径规划约束器”的角色35。对于 prerequisites 字段的设计，目前工业界与学术界存在三种截然不同的方案路线。

### **4.1 Prerequisites 字段的三种设计路线对比**

#### **方案一：存储字符串名称（string\[\]）**

* **实现机制**：直接将依赖的概念名以字符串形式硬编码，如 \["一元一次方程", "同类项合并"\]。  
* **学术与工程评估**：属于非结构化的反模式设计。极易因拼写、多义性或书本改版导致图谱断裂，且无法建立外键参照完整性，在实际生产系统中应坚决避免。

#### **方案二：存储概念唯一标识符（KC\_ID\[\]）**

* **实现机制**：基于有向无环图（DAG）的邻接表表达，存储 \["kc\_eq\_001", "kc\_term\_002"\]36。  
* **学术与工程评估**：这是工业界自适应领头羊（如 **Knewton**）的标准工程方案37。 Knewton 的底层定义极具学术借鉴意义37：  
  1. **“概念”（Concept）由其所关联的物理教学内容共同定义**（Concept is formally defined by content）37。  
  2. **“先修”（Prerequisite）定义为直接且唯一的依赖关系**（Concept A is prerequisite to Concept B if B assumes knowledge of A, and no other intermediate concept transmits this knowledge）37。  
  3. **“知识图谱”（Knowledge Graph）则是领域专家手工假设的最优图谱拓扑结构**37。 采用方案二不仅能够保证数据结构的极简与高查询效能，而且完全能够支撑确定性路径的可视化渲染36。

#### **方案三：存储概率权重/条件概率度量（Map\<KC\_ID, Probability\>）**

* **实现机制**：存储前置技能对后置技能的条件概率值或转移矩阵权重，如 {"kc\_001": 0.85, "kc\_002": 0.40}。  
* **学术与工程评估**：这是教育数据挖掘学术界的研究热点。例如 **COMMAND** 算法通过构建隐变量贝叶斯网络（Bayesian Network），从答题行为数据中发现先修关联强度39；而 **E-PRISM** 模型则在 ASSISTments 等数据集上，基于条件独立性检验计算先修强度的 Nec 指标与 CPVD 值，来度量因果关系的强度35。虽然理论完美，但如果将其作为静态元数据强行写入硬编码的底层 schema，会导致开发维护成本成倍增加，且随着学生群体的动态变化，静态概率权重极易失效。

### **4.2 Prerequisites 的工业界主流推荐模式**

针对 FoxSay 的应用场景，最合理的架构是采用“强拓扑依赖 \+ 动态自适应模型”的混合架构37：

* **数据模型层（Database Schema）**：采用方案二的升级版，即存储 KC\_ID 邻接表，但可附带一个描述因果强度的静态参考权重35。  
* **算法运行层（Runtime Model）**：自适应引擎在冷启动时，直接遵循专家手写图谱的邻接拓扑37；在系统运行积累了大量行为序列后，由后端的贝叶斯网络算法（COMMAND / E-PRISM）动态训练并计算出转移概率，用于微调推荐路径的决策权值35。

## **5\. 高利害测试场景下应试特异性字段的学术映射**

FoxSay 字段中的 exam\_frequency（考察频率）与 exam\_patterns（考察套路）具有强烈的中国应试教育场景特色。在西方主流的 K-12 自适应自备考平台（如 PrepScholar 对 SAT/ACT 的备考设计，以及学术界针对 IELTS 听力的认知诊断）中，均存在对等的学术概念和成熟的实现路径14。

### **5.1 "exam\_frequency" 的学术映射：备考信息效用与 IRT 信息函数**

在 PrepScholar 等备考自适应算法中，考试频率不会仅仅作为一个非结构化的展示标签，而是直接作为自适应收益效用（Score-Improvement Utility）的加权乘子41。

* **项目反应理论（IRT）下的信息量加权**：在自适应备考中，每个题目和知识点对最终分数的拉动效益是不同的42。系统会结合项目反应理论（IRT）中的**信息函数（Information Function）**，以及题目的历史权重，计算出每个 KC 在真实试卷中的分值占比42。  
* **自适应调度应用**：当备考学生的可用时间极度受限（例如距离真实高考或 SAT 考试仅剩 30 天）时，系统的推荐策略会发生漂移——放弃那些虽然学生尚未掌握、但考察频次极低、提分性价比极差的边缘 KC 链，转而强制将练习资源倾斜至学生处于“最近发展区”且 exam\_frequency（即测试分值权重）极高的核心核心 KC 上，以实现备考效率的最优提升41。

### **5.2 "exam\_patterns" 的学术映射：认知诊断中的多属性图谱与错误错因图式（Incorrect KCs）**

中国考试常讲的“题目套路”或“典型陷阱”，在学习科学中分别对应着**多属性认知解题路径（Multi-attribute Cognitive Pathway）和错误认知组件（Incorrect KCs/Bug Rules）**1。

* **多属性联合通路（Conjunctive Pathway）**：一个常考题型（Exam Pattern）本质上是特定情境特征（Context Elements）与多个底层 KC 节点发生 conjure 后的复合表现1。例如，高考中经典的“圆锥曲线斜率之和”题型，不仅考察圆锥曲线的基本方程，还涉及韦达定理、代数化简等多个底层 KCs 之间的联合逻辑。  
* **错因与干扰项建模（Bug Rules & Distractor Analysis）**：自顶向下的专家研究（如 Julie Booth 的代数等式解题研究）表明，优秀的智能系统必须能够识别并显式追踪学生的“错误知识组件”（Incorrect KCs）1。在考试中设计的“陷阱”（如几何题中未考虑钝角情况、代数题中未考虑分母不为零的特例），在认知诊断中被称为学生激活了特定的“错误认知图式”1。系统通过在题目的干扰项（Distractors）中埋设对应的错误 KC 标识，一旦学生选错，便能精准归因，并调取对应的针对性纠错策略1。

### **5.3 行业实证案例：均一教育平台（Junyi Academy）的“精熟度层级晋升机制”**

为了更生动地揭示应试特异性字段在真实系统中的运作机理，台湾均一教育平台（Junyi Academy）的“精熟机制”（Proficiency Mechanism）提供了一个极为经典的工程范例43：

* **精熟层级划分**：系统为每项练习（或概念节点）设计了从级别 0 到级别 4 的五级精熟度状态（以级别 4 代表完全 Proficient）43。  
* **晋升与时间锁定惩罚规则（Time-locked Spacing Effect）**：  
  1. **级别 0 ![][image20] 级别 1**：学生必须在最近的 6 次做题尝试中，正确答对 5 次，方可迈入级别 143。  
  2. **级别 1 ![][image20] 级别 2**：学生无法通过连续刷题达成。系统强制引入 **6 小时的等待冷却期**，强制引发长时记忆遗忘对抗，等待期结束后，学生必须成功通过一个包含 2 道挑战题的测验，才能晋升至级别 243。  
  3. **高级别震荡机制**：处于级别 2 的学生，若做 2 道挑战题全部正确，则晋升至级别 3；如果 2 题全部错误，则直接降级（Downgrade）回级别 1；若一正一误，则等级保持不变，要求重新发起挑战43。 这套结合了艾宾浩斯遗忘曲线、动态时间锁以及滑窗正确率评定的精熟机制，完美地将应试场景中的“巩固复习”内嵌为了可精确追踪的 schema 行为控制算法43。

下表归纳了中国应试教育行话与现代学习科学学术概念的对等关系：

| 中国高利害应试行话 (Exam Jargon) | 学习科学/认知诊断学术概念 (Scientific Jargon) | 底层运作机制与系统行为 |
| :---- | :---- | :---- |
| **考察频率 (Exam Frequency)** | 测验信息贡献权重 (Test Information Contribution)42 | 指导自适应引擎在限时备考场景下计算“提分期望回报”，进行高价值路径筛选41。 |
| **必考题型 / 经典套路 (Exam Pattern)** | 多属性联合通路与情境锚定 (Conjunctive Cognitive Pathway)14 | 定义题目需要同时激活的多个底层 KC 链，设计针对性的多步骤提示链（Hints）34。 |
| **套路陷阱 / 易错点 (Trap / Common Mistake)** | 错误知识组件与偏差图式 (Incorrect KCs / Bug Rules)1 | 建模非标准认知结构，通过设计特定的选项干扰项诊断学生在大脑中运行的错误消元规则1。 |
| **刷题巩固 / 错题本复习 (Practice & Review)** | 间隔练习效应与精熟度阻断机制 (Spacing Effect / Spaced Practice)43 | 通过引入时间锁（如均一平台的 6 小时冷却限制）和连续滑窗正确率，迫使短期记忆向长期记忆转化43。 |

## **6\. 优化版 KC Schema 建议与设计论证**

结合 FoxSay 原有设计的短板，本研究提出优化版的 KC Schema，旨在全面提升模型的理论完备度与应试场景下的算法决策效率。

### **6.1 改进版 JSON Schema**

JSON  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "title": "FoxSay\_Optimized\_KnowledgeComponent\_Schema",  
  "type": "object",  
  "required": \[  
    "id",  
    "course\_id",  
    "chapter\_id",  
    "name",  
    "cognitive\_dimension",  
    "bloom\_level",  
    "layer",  
    "definition"  
  \],  
  "properties": {  
    "id": {   
      "type": "string",   
      "pattern": "^kc\_\[a-zA-Z0-9\_\\\\-\]+$",  
      "description": "唯一标识符，采用确定性ID，确保支持有向无环图（DAG）的邻接关系查询。"  
    },  
    "course\_id": { "type": "string" },  
    "chapter\_id": { "type": "string" },  
    "name": { "type": "string" },  
      
    "cognitive\_dimension": {   
      "type": "string",   
      "enum": \["factual", "conceptual", "procedural\_skill", "procedural\_principle", "metacognitive"\],  
      "description": "契合 KLI 理论框架与修订版布鲁姆知识维度，区分事实、概念、隐性技能、有理性原理与元认知知识，指导自适应引擎在内环匹配最优的教学干预。"  
    },  
      
    "bloom\_level": {   
      "type": "string",   
      "enum": \["Remembering", "Understanding", "Applying", "Analyzing", "Evaluating", "Creating"\],  
      "description": "完整采纳修订版布鲁姆认知水平分类，为大语言模型（GenAI）时代的高阶思维和批判性评价留下评估空间。"  
    },  
      
    "layer": {   
      "type": "string",   
      "enum": \["micro", "meso", "macro"\],  
      "description": "划分知识组件的粒度。DataShop 证实过粗或过细均会影响自适应拟合效果，此字段用于支持在多尺度视图下聚合分析。"  
    },  
      
    "definition": { "type": "string" },  
    "formula": { "type": "string" },  
    "intuition": { "type": "string" },  
      
    "conditions": {  
      "type": "array",  
      "items": { "type": "string" },  
      "description": "该技能激活的必要与充分检索特征（Retrieval Conditions），用于判定 Feature-to-Response 的边界。"  
    },  
      
    "key\_properties": {  
      "type": "array",  
      "items": { "type": "string" }  
    },  
      
    "examples": {  
      "type": "array",  
      "items": {  
        "type": "object",  
        "required": \["example\_id", "content\_type"\],  
        "properties": {  
          "example\_id": { "type": "string" },  
          "text": { "type": "string" },  
          "content\_type": { "type": "string", "enum": \["text", "video", "worked\_example"\] },  
          "resource\_url": { "type": "string" }  
        }  
      },  
      "description": "显性关联的外部教学资源，对应 KLI 理论中的 Instruction 实体。"  
    },  
      
    "common\_mistakes": {  
      "type": "array",  
      "items": {  
        "type": "object",  
        "required": \["mistake\_id", "description"\],  
        "properties": {  
          "mistake\_id": { "type": "string" },  
          "description": { "type": "string" },  
          "associated\_bug\_rule\_id": {   
            "type": "string",   
            "description": "指向特定的错误知识组件（Incorrect KC ID），用于在认知诊断模型中进行偏差图式归因。"   
          }  
        }  
      }  
    },  
      
    "prerequisites": {  
      "type": "array",  
      "items": {  
        "type": "object",  
        "required": \["prerequisite\_kc\_id", "dependency\_strength"\],  
        "properties": {  
          "prerequisite\_kc\_id": { "type": "string" },  
          "dependency\_strength": {   
            "type": "number",   
            "minimum": 0,   
            "maximum": 1,   
            "description": "依据 COMMAND 贝叶斯网络或 E-PRISM 条件独立性测试学出的依赖强度，1.0 代表强先修约束。"   
          }  
        }  
      },  
      "description": "有向图先修邻接关系，结合静态依赖权重以支持弹性的图寻路决策。"  
    },  
      
    "related\_kcs": {  
      "type": "array",  
      "items": { "type": "string" },  
      "description": "属于横向关联，具备相似认知负荷、但不构成硬性先修依赖的其他概念节点。"  
    },  
      
    "exam\_oriented\_metadata": {  
      "type": "object",  
      "description": "针对高利害备考场景度身定制的测量学元数据。",  
      "properties": {  
        "exam\_utility\_weight": {   
          "type": "number",   
          "minimum": 0,   
          "maximum": 1,  
          "description": "该概念对应提分回报的信息量权重。临考冲刺时，算法借此优先调度高回报率节点。"   
        },  
        "irt\_difficulty\_beta": {   
          "type": "number",   
          "description": "项目反应理论中的先验难度 beta 值，作为 AFM 算法拟合的底层初始参数。"   
        },  
        "target\_exam\_patterns": {  
          "type": "array",  
          "items": {  
            "type": "object",  
            "required": \["pattern\_id", "pattern\_name"\],  
            "properties": {  
              "pattern\_id": { "type": "string" },  
              "pattern\_name": { "type": "string" },  
              "cognitive\_scaffolding\_path": {   
                "type": "string",   
                "description": "描述拆解该应试套路的多步骤联合认知路径（Conjunctive Paths）。"   
              },  
              "difficulty\_level": { "type": "string", "enum": \["Elementary", "Junior", "Senior"\] }  
            }  
          }  
        }  
      }  
    }  
  }  
}

### **6.2 核心改造的学术理由与设计论证**

* **引入 cognitive\_dimension 字段（契合 KLI 理论一致性）**： Koedinger 等人的 KLI 理论强调，“不同的知识组件类型要求匹配不同的教学干预手段”44。将认知维度划分为事实、概念、隐性技能（Procedural Skill，通过行为建模训练）与有理性原理（Procedural Principle，通过解释性问答理解）1，能够支持系统自动建立“知识属性 \- 学习事件 \- 教学设计”的一致性控制逻辑45。对事实类知识倾向于推送间隔复习，而对原理类知识强制进行 Worked Examples 与自我解释（Self-explanation）引导46。  
* **重构 prerequisites 为嵌套关系对象（支撑动态寻路）**： 摒弃平面化的列表，在邻接表中显式定义 dependency\_strength（依赖强度）35。这既吸收了 Knewton 在工业界定义的“高置信度直接先修图谱”37，又契合了学术界利用 COMMAND 和 E-PRISM 算法计算因果依赖关系强度的实践35。在推荐路径受阻时，寻路引擎可以通过降低强度阈值，寻找侧向学习替代路径。  
* **合并封装应试元数据并改造为定量属性 exam\_utility\_weight（赋能自适应提分策略）**： 将原有的平面展现层标签 exam\_frequency 升级为面向计算的权重值41。该值是试卷在 IRT 测试中贡献的 Fisher 提分信息量的直接映射42。在资源和时间受限的冲刺模式下，该字段能充当自适应背包调度算法（Knapsack-like Scheduling）的价值乘子，使提分效用最大化41。  
* **将常考题型映射为带有联合路径的 target\_exam\_patterns**： 每一个 Pattern 不仅是一个名字，还关联了 cognitive\_scaffolding\_path。在认知诊断中，这用于描述当学生卡在某一综合考试题型中时，内环应当如何为其动态生成多维的提示链（Hints），或者将综合套路题降级拆解为单步基础 KC 练习34。

## **7\. 开源教学 KC 数据集的对照与冷启动利用**

为了验证改进版 Schema 的完备性，并为 FoxSay 系统在缺少大规模交互日志的冷启动期提供可复用的元数据图谱或测验基准，建议引入全球四大主流的学习科学公开数据集进行对照和利用。  
下表对这四大开源数据集进行了深度对比与架构拆解：

| 数据集名称 | 主办机构与授权 | 核心认知层次与特点 | Schema 字段与实体映射关系 | FoxSay 检验与冷启动利用价值 |
| :---- | :---- | :---- | :---- | :---- |
| **ASSISTments** (2009-2010, 2012-2013) | 伍斯特理工学院 (WPI) 开放访问34 | \* 覆盖中小学数学，主攻 Applying、Analyzing 层次34。 \* **核心特征**：记录了极佳的学生首步尝试（First attempt）及多步骤 Scaffolding 互动序列34。 | assignment\_id, user\_id, problem\_id, original (主问题/脚手架子问题标志), correct (首答对错), skill\_name, opportunity34。 | \* **极高。** \* 可用于验证 FoxSay 内环步骤设计的对错诊断及滑窗正确率（Opportunity Count）计算逻辑9。 \* 尤其是其“首答错误则调出 Scaffolding 步骤”的模式，可直接用来测试 FoxSay 中 layer (micro/meso) 级概念之间的转化控制34。 |
| **Junyi Academy** (均一教育数据集) | 均一教育平台基金会 (CC BY-NC-SA 4.0)50 | \* 覆盖 K-12 理科体系，高度契合东亚应试教育大纲43。 \* **核心特征**：附带完整的专家手写级先修知识树（Knowledge Tree）和严密的等级精熟度机制43。 | Log\_Problem (答题日志，含 Round 精度时间戳), Info\_Content (包含 Elementary, Junior, Senior 三级难度), Info\_UserData43。 | \* **无可替代的冷启动源。** \* 由于两岸大纲具有高度的一致性，FoxSay 可直接爬取并复用其理科 prerequisites 先修结构与难度属性（Info\_Content）51。 \* 极其适合用作冷启动期 exam\_patterns 难易度分类的先验模板43。 |
| **KHANQ / Khan Academy** 语料库 | 俄亥俄州立大学 / 汗萨学院开放授权52 | \* 主攻 Understanding、Analyzing 以及 Evaluating52。 \* **核心特征**：包含由真实学习者提出、旨在深度理解概念的 1,034 个高质量深层追问三元组52。以及 Khanmigo 2024 Math Tutoring 评估交互集32。 | Context (教学内容独立段落), Prompt (学生背景知识), Question (要求深层推理的提问)52。 | \* **极高（专攻高阶思维验证）。** \* 可直接用于检验 FoxSay 在 bloom\_level 补全为 Evaluating / Creating 后的内容对齐效果52。 \* 用于测试智能 AI Tutor 在面对学生真实高阶疑问时的反馈生成能力32。 |
| **OpenStax & CK-12** 语义图谱集 | 莱斯大学 / CK-12 基金会，学术开放54 | \* 涵盖 K-12 全学段多学科，偏向 Remembering / Understanding54。 \* **核心特征**：具有最标准的教科书编排级三级分类体系（Subject \- Chapter \- Topic）54。 | K12-BERT、K12-SentBERT 预训练语料，标准 JSON 的 creationDateTime, columns\_metadata54。 | \* **中等偏上。** \* 提供多学科标准化 Body of Knowledge (BoK) 的元数据对齐基准56。 \* 适合用作 FoxSay 系统中 macro 与 meso 层级分类的标准对齐工具。 |

## **8\. "如果只能改 3 处" 的优先级推荐与实施路线**

若在 FoxSay 项目当前的开发周期内受限于工程人力或交付排期，建议放弃面面俱到的重构，优先执行以下 3 处最具理论提拉效应与工程收益的核心修改：

### **第一优先级：重构 prerequisites 为“唯一标识符邻接表 \+ 依赖强度”结构（方案二扩展版）**

* **改动要点**：在 schema 中彻底杜绝中文或英文的文本名称。将 prerequisites 改为对象数组，存储 prerequisite\_kc\_id（字符串 ID）以及 dependency\_strength（静态浮点权重，冷启动期设为 1.0）35。  
* **科学依据**：这是确保自适应路径图谱可计算的基石15。存储 ID 可以支撑快速的图查询与路径渲染36；而保留 dependency\_strength 则为后续无缝迁移至 COMMAND、E-PRISM 等贝叶斯网络条件依赖概率算法做好了数据兼容准备，确保底层架构在算法演进时无需经历大修35。

### **第二优先级：封装扩展 exam\_oriented\_metadata 元数据块，将平面频率标签演进为 exam\_utility\_weight**

* **改动要点**：将散落的、纯展示层标签 exam\_frequency（考察频率）封装进一个独立的测量学对象中，改名为 exam\_utility\_weight 并进行定量化设计41。  
* **科学依据**：这是备考系统自适应寻路算法产生“业务溢价”的核心41。借鉴西方高利害备考系统 PrepScholar 的“分值期望收益”控制方法，定量化的效用权重能在临考前夕作为调度决策的惩罚/奖励参数，指导寻路引擎绕开低频废题，优先补救高频高产的核心概念链，从而将系统从“刷题库”升级为具有真正高临床提分价值的自适应备考产品41。

### **第三优先级：全面补齐布鲁姆分类法至 6 阶，并引入 cognitive\_dimension 知识属性**

* **改动要点**：将 bloom\_level 补齐为标准的 6 级（加入 Evaluating 与 Creating）24；同时在顶级层增加 cognitive\_dimension（事实、概念、程序技能、有理性原理、元认知）标签30。  
* **科学依据**：这是大语言模型（GenAI）时代高阶思维评定的刚性保障27。根据 Koedinger 提出的 KLI 核心框架，系统的“干预动作”必须与“知识本性”保持高度的 pedagogical 契合度（例如，对事实类 KCs 自动调用 Spaced Review 策略，对原理类 KCs 自动启用 AI-Tutor 自我解释苏格拉底对话机制）44。此字段的设立打通了系统针对高能力段学生（掌握率 ![][image19]）的个性化分流能力，避免了传统 ITS 的天花板瓶颈29。

#### **引用的著作**

1. Knowledge component \- Theory Wiki \- LearnLab, [https://learnlab.org/mediawiki-1.44.2/index.php?title=Knowledge\_component](https://learnlab.org/mediawiki-1.44.2/index.php?title=Knowledge_component)  
2. Designing for metacognition—applying cognitive tutor principles to the tutoring of help seeking \- PACT Center, [https://pact.cs.cmu.edu/koedinger/pubs/Roll,%20Aleven,%20Koedinger%2007.pdf](https://pact.cs.cmu.edu/koedinger/pubs/Roll,%20Aleven,%20Koedinger%2007.pdf)  
3. The Behavior of Tutoring Systems \- SciSpace, [https://scispace.com/pdf/the-behavior-of-tutoring-systems-5kg9j77coc.pdf](https://scispace.com/pdf/the-behavior-of-tutoring-systems-5kg9j77coc.pdf)  
4. Ontology-Based Layered Hybrid AI-Driven Knowledge Model for Personalized E-Learning, [https://www.mdpi.com/2227-7390/14/5/808](https://www.mdpi.com/2227-7390/14/5/808)  
5. External Tools \- DataShop @CMU, [https://pslcdatashop.web.cmu.edu/ExternalTools?toolId=10](https://pslcdatashop.web.cmu.edu/ExternalTools?toolId=10)  
6. A Comparison of Model Selection Metrics in DataShop \- Educational Data Mining, [https://www.educationaldatamining.org/EDM2013/papers/rn\_paper\_48.pdf](https://www.educationaldatamining.org/EDM2013/papers/rn_paper_48.pdf)  
7. DataShop \> About, [https://datashop.ethz.ch/about/](https://datashop.ethz.ch/about/)  
8. In the Additive Factors Model (AFM), the probability student i gets... \- ResearchGate, [https://www.researchgate.net/figure/n-the-Additive-Factors-Model-AFM-the-probability-student-i-gets-step-j-correct-p-ij\_fig1\_266502553](https://www.researchgate.net/figure/n-the-Additive-Factors-Model-AFM-the-probability-student-i-gets-step-j-correct-p-ij_fig1_266502553)  
9. About \- DataShop @CMU, [https://pslcdatashop.web.cmu.edu/about/](https://pslcdatashop.web.cmu.edu/about/)  
10. Dataset: Junyi Academy Math Practicing Log (to Jan. 2015\) Partial Samples \- DataShop @CMU, [https://pslcdatashop.web.cmu.edu/DatasetInfo?datasetId=1275](https://pslcdatashop.web.cmu.edu/DatasetInfo?datasetId=1275)  
11. DataShop \> Help \> Import Format (Tab-delimited), [https://pslcdatashop.web.cmu.edu/help?page=importFormatTd](https://pslcdatashop.web.cmu.edu/help?page=importFormatTd)  
12. The Q-matrix Method: Mining Student Response Data for Knowledge \- AAAI, [https://cdn.aaai.org/Workshops/2005/WS-05-02/WS05-02-006.pdf](https://cdn.aaai.org/Workshops/2005/WS-05-02/WS05-02-006.pdf)  
13. Statistical Analysis of Q-matrix Based Diagnostic Classification Models, [https://sites.stat.columbia.edu/jcliu/paper/DCMStat.pdf](https://sites.stat.columbia.edu/jcliu/paper/DCMStat.pdf)  
14. Constructing and Validating a Q-matrix for Cognitive Diagnostic Analysis of the Listening Comprehension Section of the IELTS \- ERIC, [https://files.eric.ed.gov/fulltext/EJ1463868.pdf](https://files.eric.ed.gov/fulltext/EJ1463868.pdf)  
15. Adaptive Learning AI: Unlocking Personalized Student Paths (2026) | AGIX Technologies, [https://agixtech.com/insights/adaptive-learning-ai-personalized-paths-for-every-student/](https://agixtech.com/insights/adaptive-learning-ai-personalized-paths-for-every-student/)  
16. Attentive Q-Matrix Learning for Knowledge Tracing \- arXiv, [https://arxiv.org/pdf/2304.08168](https://arxiv.org/pdf/2304.08168)  
17. Calibrated Q-Matrix-Enhanced Deep Knowledge Tracing with Relational Attention Mechanism \- MDPI, [https://www.mdpi.com/2076-3417/13/4/2541](https://www.mdpi.com/2076-3417/13/4/2541)  
18. ACE: AI-Assisted Construction of Educational Knowledge Graphs with Prerequisite Relations, [https://jedm.educationaldatamining.org/index.php/JEDM/article/download/737/218](https://jedm.educationaldatamining.org/index.php/JEDM/article/download/737/218)  
19. Continual Pre-Training of Language Models for Concept Prerequisite Learning with Graph Neural Networks \- MDPI, [https://www.mdpi.com/2227-7390/11/12/2780](https://www.mdpi.com/2227-7390/11/12/2780)  
20. HetGNN-KGAT: Enhancing Personalized Course Recommendation in MOOCs With Knowledge Graph Attention Networks \- Aaltodoc, [https://aaltodoc.aalto.fi/bitstreams/f9f82b46-d161-432d-b981-694c39b19ede/download](https://aaltodoc.aalto.fi/bitstreams/f9f82b46-d161-432d-b981-694c39b19ede/download)  
21. HetGNN-KGAT: Enhancing Personalized Course Recommendation in MOOCs with Knowledge Graph Attention Networks \- ResearchGate, [https://www.researchgate.net/publication/397475772\_HetGNN-KGAT\_Enhancing\_Personalized\_Course\_Recommendation\_in\_MOOCs\_with\_Knowledge\_Graph\_Attention\_Networks](https://www.researchgate.net/publication/397475772_HetGNN-KGAT_Enhancing_Personalized_Course_Recommendation_in_MOOCs_with_Knowledge_Graph_Attention_Networks)  
22. DataShop \> Files, [https://pslcdatashop.web.cmu.edu/Files?datasetId=76](https://pslcdatashop.web.cmu.edu/Files?datasetId=76)  
23. Downloads \- DataShop @CMU, [https://pslcdatashop.web.cmu.edu/about/downloads.html](https://pslcdatashop.web.cmu.edu/about/downloads.html)  
24. Blooms Taxonomy | CITT \- University of Florida, [https://citt.it.ufl.edu/resources/course-development/the-learning-process/designing-the-learning-experience/blooms-taxonomy/](https://citt.it.ufl.edu/resources/course-development/the-learning-process/designing-the-learning-experience/blooms-taxonomy/)  
25. Bloom's taxonomy of cognitive learning objectives \- PMC \- NIH, [https://pmc.ncbi.nlm.nih.gov/articles/PMC4511057/](https://pmc.ncbi.nlm.nih.gov/articles/PMC4511057/)  
26. Reimagining Flipped Learning via Bloom's Taxonomy and Student–Teacher–GenAI Interactions \- MDPI, [https://www.mdpi.com/2227-7102/15/4/465](https://www.mdpi.com/2227-7102/15/4/465)  
27. (PDF) Cultivating independent thinkers: The triad of artificial intelligence, Bloom's taxonomy and critical thinking in assessment pedagogy \- ResearchGate, [https://www.researchgate.net/publication/389776892\_Cultivating\_independent\_thinkers\_The\_triad\_of\_artificial\_intelligence\_Bloom's\_taxonomy\_and\_critical\_thinking\_in\_assessment\_pedagogy](https://www.researchgate.net/publication/389776892_Cultivating_independent_thinkers_The_triad_of_artificial_intelligence_Bloom's_taxonomy_and_critical_thinking_in_assessment_pedagogy)  
28. The triad of artificial intelligence, Bloom's taxonomy and critical thinking in assessment pedagogy, [https://d-nb.info/1366859596/34](https://d-nb.info/1366859596/34)  
29. EduMSRA: A Multi-Source Educational Research Agent Integrating Retrieval-Augmented Generation and Model Context Protocol for Adaptive Intelligent Tutoring Systems \- MDPI, [https://www.mdpi.com/2076-3417/16/9/4400](https://www.mdpi.com/2076-3417/16/9/4400)  
30. Bloom's Taxonomy of Educational Objectives | Center for the Advancement of Teaching Excellence | University of Illinois Chicago, [https://teaching.uic.edu/cate-teaching-guides/syllabus-course-design/blooms-taxonomy-of-educational-objectives/](https://teaching.uic.edu/cate-teaching-guides/syllabus-course-design/blooms-taxonomy-of-educational-objectives/)  
31. Bloom's Taxonomy Learning Activities and Assessments | Centre for Teaching Excellence, [https://uwaterloo.ca/centre-for-teaching-excellence/resources/teaching-tips/blooms-taxonomy-learning-activities-and-assessments](https://uwaterloo.ca/centre-for-teaching-excellence/resources/teaching-tips/blooms-taxonomy-learning-activities-and-assessments)  
32. Introducing a New Dataset to Further the Field of AI Research \- Khan Academy Blog, [https://blog.khanacademy.org/introducing-a-new-dataset-to-further-the-field-of-ai-research/](https://blog.khanacademy.org/introducing-a-new-dataset-to-further-the-field-of-ai-research/)  
33. The Knowledge-Learning-Instruction (KLI) Framework: Toward Bridging the Science-Practice Chasm to Enhance Robust Student Learni \- PACT Center, [https://pact.cs.cmu.edu/pubs/PSLC-Theory-Framework-Tech-Rep.pdf](https://pact.cs.cmu.edu/pubs/PSLC-Theory-Framework-Tech-Rep.pdf)  
34. Imputing KCs with Representations of Problem Content and Context \- eScholarship.org, [https://escholarship.org/content/qt94x3f95v/qt94x3f95v\_noSplash\_74143f673a0e78cc37ff01c068e153b7.pdf](https://escholarship.org/content/qt94x3f95v/qt94x3f95v_noSplash_74143f673a0e78cc37ff01c068e153b7.pdf)  
35. Discovering prerequisite relationships between knowledge components from an interpretable learner model \- Educational Data Mining, [https://educationaldatamining.org/EDM2023/proceedings/2023.EDM-posters.55/index.html](https://educationaldatamining.org/EDM2023/proceedings/2023.EDM-posters.55/index.html)  
36. cjrd/kmap: Knowledge map visualization library \- GitHub, [https://github.com/cjrd/kmap](https://github.com/cjrd/kmap)  
37. Glossary | dev.knewton.com, [https://dev.knewton.com/implementation/glossary/](https://dev.knewton.com/implementation/glossary/)  
38. API Overview | dev.knewton.com, [https://dev.knewton.com/implementation/api-overview/](https://dev.knewton.com/implementation/api-overview/)  
39. Joint Discovery of Skill Prerequisite Graphs and Student Models \- Iowa State University, [https://faculty.sites.iastate.edu/jtian/files/inline-files/edm-16.pdf](https://faculty.sites.iastate.edu/jtian/files/inline-files/edm-16.pdf)  
40. (PDF) Discovering Prerequisite Relationships among Knowledge Components, [https://www.researchgate.net/publication/320172526\_Discovering\_Prerequisite\_Relationships\_among\_Knowledge\_Components](https://www.researchgate.net/publication/320172526_Discovering_Prerequisite_Relationships_among_Knowledge_Components)  
41. What Is Adaptive Test Prep? How It Works and Why It's So Effective \- PrepScholar Blog, [https://blog.prepscholar.com/what-is-adaptive-test-prep](https://blog.prepscholar.com/what-is-adaptive-test-prep)  
42. How Does Adaptive Testing Work in the Digital SAT? \- Test Ninjas, [https://test-ninjas.com/digital-sat-adaptive-testing](https://test-ninjas.com/digital-sat-adaptive-testing)  
43. Junyi Academy Online Learning Activity Dataset \- Kaggle, [https://www.kaggle.com/datasets/junyiacademy/learning-activity-public-dataset-by-junyi-academy/data?select=Log\_Problem.csv](https://www.kaggle.com/datasets/junyiacademy/learning-activity-public-dataset-by-junyi-academy/data?select=Log_Problem.csv)  
44. KLI: A Theoretical Framework for Improving Student Learning \- Global Learning Council, [https://www.globallearningcouncil.org/posts/kli-a-theoretical-framework-for-improving-student-learning/](https://www.globallearningcouncil.org/posts/kli-a-theoretical-framework-for-improving-student-learning/)  
45. The knowledge-learning-instruction framework: bridging the science-practice chasm to enhance robust student learning \- PubMed, [https://pubmed.ncbi.nlm.nih.gov/22486653/](https://pubmed.ncbi.nlm.nih.gov/22486653/)  
46. Different Goals Imply Different Methods: A Guide to Adapting Instructional Methods to Your Context \- University of New Hampshire, [https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-05/itow-different-goals-imply-different-methods-koedinger-rau-mclaughlin.pdf](https://www.unh.edu/teaching-learning-resource-hub/sites/default/files/media/2023-05/itow-different-goals-imply-different-methods-koedinger-rau-mclaughlin.pdf)  
47. Using the Knowledge-Learning-Instruction Framework to Design Effective Learning | Dr. Ken Koedinger \- YouTube, [https://www.youtube.com/watch?v=bHWBlC4SRro](https://www.youtube.com/watch?v=bHWBlC4SRro)  
48. Theories to use in Computing Education Research \- Daphne Miedema, [https://daphnemiedema.nl/2023/08/04/learnlab.html](https://daphnemiedema.nl/2023/08/04/learnlab.html)  
49. ASSISTmentsData \- 2009-2010 ASSISTment Data, [https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data](https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data)  
50. Junyi Academy Online Learning Activity Dataset \- Kaggle, [https://www.kaggle.com/datasets/junyiacademy/learning-activity-public-dataset-by-junyi-academy](https://www.kaggle.com/datasets/junyiacademy/learning-activity-public-dataset-by-junyi-academy)  
51. SingPAD: A Knowledge Tracing Dataset Based on Music Performance Assessment, [https://educationaldatamining.org/edm2024/proceedings/2024.EDM-short-papers.30/index.html](https://educationaldatamining.org/edm2024/proceedings/2024.EDM-short-papers.30/index.html)  
52. KHANQ: A Dataset for Generating Deep Questions in Education \- ACL Anthology, [https://aclanthology.org/2022.coling-1.518/](https://aclanthology.org/2022.coling-1.518/)  
53. KHANQ: A Dataset for Generating Deep Questions in Education \- ACL Anthology, [https://aclanthology.org/2022.coling-1.518.pdf](https://aclanthology.org/2022.coling-1.518.pdf)  
54. arXiv:2205.12335v1 \[cs.CL\] 24 May 2022, [https://arxiv.org/pdf/2205.12335](https://arxiv.org/pdf/2205.12335)  
55. 1.3 Data and Datasets \- Principles of Data Science | OpenStax, [https://openstax.org/books/principles-data-science/pages/1-3-data-and-datasets](https://openstax.org/books/principles-data-science/pages/1-3-data-and-datasets)  
56. DK-PRACTICE: An Intelligent Platform for Knowledge Tracing and Educational Content Recommendation: A Case Study in Higher Education \- MDPI, [https://www.mdpi.com/2078-2489/17/2/202](https://www.mdpi.com/2078-2489/17/2/202)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAcAAAAcCAYAAACtQ6WLAAAAl0lEQVR4XmNgGOpAEIgZ0QVBgBWI/wOxJ7oECAgD8XMg1kSXgAEOdAG8QAWITwPxayCWR5bgAeIVQGwGxKZAXIQs6QLE/QwQ56cDcQSyJMjZIB2cQLwDiBWRJWFAB4jfM+AIgAYg/ocuCAL8QHwCiK8DsTIQByJL+jJAgg1EL2eAhBQcyDBAdO0HYhNkCRgABZskuuAwAQBeMhIecZlDswAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAcCAYAAAC3f0UFAAAA8klEQVR4Xu3RL24CURDH8RGQQAq0pKSEpBcgiCpMdQ0GU0MQOMIROAEGSxruQLCAQawkQXEARAkWW9GEP9/Z9zZdHg9Tvb/kk7Azs8vOW5Ek/rxhh1/0nN5NSljjB3Wn540Ob1F2G74cMEXKbfhyRt8t+pLHHq/2Wt97gwVy0VCUKmbI4AMj1PCNSmwuTBMDvGOILBpY4TE2F0YHJ/jCg62lxfNUbS7FLKjH1xbzZG90KV2uiC6OGMudI9SFTva3bh7I32IdWwujd+uH0A+iiV4pQAEtWw/zLOY8tRnlU8zNczFLXuVJzPnGo3/94tSS/C8X47QkiwQdlx4AAAAASUVORK5CYII=>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAABcUlEQVR4Xu2UvytGURjHH6EoBr+SGAxKQgqLsrxlZbAyyMJsQFL8AZKMUgbJwGARo7IoKxlQ/AEymfl8O+dynTfc+763LPdTn973Pk+nc85znnPMcnL+i2rcSegqNrph6Vmy4sFTeI0Nf8QSU4vHQawC93A7iI/jKdYE8UT04UEQ04q1cu0gzqQVT56YGZwPYkP4hj1BfAHngljJRGV7DxNZ04y3VtpEqc4uKttLmIjRgYv+vxZ2aW5hqc5PZ6BBaoaf0Fndxb6jKqhZEhEvW9hxv6GJU92veNnCjhODeIL3OOZjVebuocqmRtrHM2zy+SLqcM3cbm6w81vWsYFteGFuF6Idn3AaZ3EXH7HV5z9RQAlNEKoyqpwRBRzBZ3MXXYziKx7iAHZhv8+VxTqem3u6hHb2gEf+NxN0LtqNVr1iX9WIGkePcwsumzu7kunFK9w098CqedTm3T4/gVs47L/LQrdfjSMqsT6WE1EuJxs+ACCUSPEodRtvAAAAAElFTkSuQmCC>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAaCAYAAACO5M0mAAAAsUlEQVR4XmNgGAWogBWIhdAF0YE6EL8E4uvoEtiAABBzoAuSBXiAWBiIGdElYADk+BwGiAJfIP4PxOkoKqDAlQGiGASqGCAKoxHSCAATBHlgKxB/BWJjhDQmkAbiB0B8GogFUaVQQTkDHvfBAAsQr2GgprUuQPwPiOcz4AlHEIC5D2uwvAbiT0CsD8Q/gXg6A8StGOA3EJ8B4gggXg3E/KjSCBAMxLOAeBIQM6PJDQYAALJWG8vYf2ePAAAAAElFTkSuQmCC>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABcAAAAaCAYAAABctMd+AAABbUlEQVR4Xu2TvyuFYRTHj6IockUkBu4i+VEYpKQUg8Ed/JhQdzNZDJSJweYvsAjDHQwMYjEoBnXXK8Od7nQnTGa+387zvh3Pe916UVLvpz7DOc9zn/c85zlXJCEh4X/QCmtM3OjF36IZXsIsfIevcFn04HNYgO3B5rhMwhO4L3p41qxtu9ycycViVvTHN/AZ9pu1Y9HD+ZGALdHbWurgBhz28iFleAebTI4xD583uSfYbWIyDl9gxsuH8JCFCrkcrPXysaiHb3DM5BpEH3fExaPwAs6EO5RTeA/35IvpSotWuepibmJvF13MHh/ATrjpcoRTxH6vw1vR8Y3Aaq7hAzwT7fWjWe+B03ACDpr8kGghR86KlXMMV0Sr6JDoHypgV7RdlhaYF60+AlvCSeGmavB2JbgDe02eRfGWbSYXEozbIZzy1iwDom2zY0mqtmTJ2OWt+XCqfNgSVv9r8E2u4Boswr7Pyz8nJfr4f8MHjIM5aXaXXDsAAAAASUVORK5CYII=>

[image6]: <data:image/png;base64,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>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAZCAYAAAA4/K6pAAABLUlEQVR4Xu3TTysFURjH8Z+wkCvJv25sbBSJZKUsLa6NhbwA70HxCqxZWClZKrwAyUJZUCxZSVHKQihli+/Tc657xszcYWEjv/rUzDPPOTPnzIz0n1/JME5xgV20Jy/XzzTusYAB3GE5bqiXcTxjC80o4Siw48IcyCcYCefVCW5RDrXc2DrfMRvVhvAoX0Z/VM/MFG7QF9Vm5JNeoiuqZ2YFD/L1bwTn8gn20FRrTacVhzhRbbCx/bAJCt/CGF6UXqcN3kdLOO/FFRY/O0Im8Iq2qGaD3lCJarmp7na8zknsyL+HwjRgTf6IdryEp0SHNC9/xbYE60ulW76Jx/L/YDB5WXPYxrr8JpnpQafyG671zT3Jy5n8SUdV8F1kxZ5qE6v64e8dpwONX4t/IB8bhTMtGN7ibQAAAABJRU5ErkJggg==>

[image8]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAZCAYAAADe1WXtAAABZElEQVR4Xu2UMShGURTHj1AUipQBJZtSlGQxMoiJwaAsBpmMym4QSUpGSRRJbDbZlMFCioFJySBKmeR3Ou9+7nf6Hu+ziV/96nv/d7777rvn3ifyz6+mFK9xB8/xBjvzKoqkHBewMrkuwXk8zVX8gFFcddkMvrosMw14gM0un8MXl2WiArexy+U68zfsd3kmmnBfbJbr+CjWoAccjOqKog8XsQqXxBqzLDb4SFRXFLM45jLtvM76Smy9Y3SXfMsh1vpQrEnvYm8SWMGt6DqVNR9AGe6Jdb4jyfTBZzgZir5C96KnHZ/wSD4Pgw5+j72hKI1WvMCWKJvGZxyOsrDGOvseHBJbmoGoJoeul964EzvvG7grts1iwquf4DjWiM24YNO0GYre1C77TgfCq+tDbyVlMEVP0qYPU9Atd4n12C32kMbEPMKmz8IxTiS/dWn0f1Nia51HW2IWqsW+tYE6KTDgH+cDCXo3ZMN8o4EAAAAASUVORK5CYII=>

[image9]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABQAAAAZCAYAAAAxFw7TAAABC0lEQVR4XmNgGAWjYAQAASAWBmJGdAlywHUg/g/Fl9DklIBYCE0MLwhmgBj0DIh/Qdkgl4IAyLV9UDZRQBuIHwExN5TPDMSBQBwB5asA8XYoGwZY0fgogJ8Bu4JDQGwJxDuAWBxJfBIQL0XiEw3WMkA0NiCJCQLxaSBORxIjGswH4tdArIMkps8ACWcbJDGiAchAWDiCAChyQGJrgNgciH2A+B8QeyKpwQsOM0BcBAMw7x4E4jgg5mOAuBRb+GMFoLSIHBkw7y4E4vsMJBgEA1uBmAOJHw3EV4FYBIhNGSAWSEMxQSDDgBnw+4E4GcoGyfcAcSYDkdkUZDsPmhgvAyTRwwAoKxJl2DAHAOIDJPkTbbqHAAAAAElFTkSuQmCC>

[image10]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAaCAYAAACtv5zzAAABiElEQVR4Xu2UvytGURjHH6GQH+GNgYVBWSiSlFdWxWZTFgOSf8B/oFiUkkgGA3knSaRkU0oGNlIGJiPFgO+35xye91z3Dhik+61P773fc+85z/me574iqVKl+p8qBHXmvsx5P9YpOAeN7v4avIENUOAf+q6qwDPIGm9RdIFx48WpODRCTYBdUGK8Q/AEuoxHtYFpdz0LXsDl53BUrP5EopXei76YMV6RaGQHxltwXqw6waPkT0QxnpHAC9UO7kBvOGDVCh5AufFqRRfl4l4zYBOcgRbnsQC/yyVwDPrd2IdKwQ5ocPc1ICfaVdX+IdEqOREnHBLtrDWwDbrBIHgFA/4FK7bmBVgHV2BfNFsvHj7z545u3S8XZxGsehRUihYR21GMpV70gRX5On8bic+fRd1IwsShekS/iYrA9xX7bmMRjMfvrBlMgSY3HlEfWBaNih20Kvl52nioIzDmrhnxHJiUhK++AwwH+IOnGI89eO7Q/kexOWInTxIn3gNbYD4Y+xXx8Hj4f1PvC+hC8Buc/o0AAAAASUVORK5CYII=>

[image11]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAD4AAAAaCAYAAADv/O9kAAACAklEQVR4Xu2Wu0tcQRTGPyGKIVHwgSLRLigWmkLBRjsbERMIFgGt0miTJo3ivyA21qZIEXw2FqJYXYhdIFYSCAbFIikDopX4+D7PrDt7F5dZWbjuen/wY/fOQ/fMnDNzgZSUlJSUlMdOG62PN1YiL+gKPaOX9JqO5YyoUKpokzPCEwrcJ8IDA6+mze67VrLG6ysHIhQZ+B+6RJ+75yt6QQfvRpSGRvqOjgc6CqvhUCIUEbhq4y997bX9osf0ldd2H7XxhgI8qsBn6GKs7ZxuIT+oXvoJVg7fYf8kPjdJIgQGrgAO6HCsXZO1ID7P6De6654zc9/fjUieCIGB98F296XX1oCwNP9Mf8DGh9JD/8N+XIhHtON2ZhgRAgN/Q09jbUPIT/M5ukp/0k7Y7m/A0lynv+pxG3ZeJEmEwMB1iu8gu2s64H4jP811umdSW39U2XBMJ+lHOgC7GVrd+KTYhwU+DbuaC9INO6g26R5ssl/z2nntsMrixH1qIZSyy7CsEUrjpPiK/DKR+q0FaUH2tU91257bfcsEbMe186rvQ7ruPke8cWXJFGyl4qgUtCDqF0prLYRQWajeZ2GZUVZ8oF/oP1jg87AsyOCnudALTpf7/hZWIv3uuazQ4eS/MSl1M6+vQrvrX111Xp/wr8OKQAHrmlqjC7G+ikZXQtJXVEqpuAG0rnOJvJy4PgAAAABJRU5ErkJggg==>

[image12]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAoAAAAbCAYAAABFuB6DAAAAvklEQVR4Xu3QvQ4BQRSG4SOhkEj8Fxq9SqFT6BUKFYnGVXAFLkNEr6MWNbWeC9BIKBR4J+NMxooMrfiSpzhnvuzOrsg/XySDOspIRM5ccthhjAUOaPoFkyTmKD7mGPo4akGXE1z9JUlhhYoustjgpAsvU7R0KGEv74tDHcyjzcWDxZrYUrBYFft1weLHd4xjhps7ttHfY67m0pXXYgFbpP1lHuvIsoOLN7uY37REDyOcMXhqeGmILbbFvuU3cwep3CZbyykkVQAAAABJRU5ErkJggg==>

[image13]: <data:image/png;base64,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>

[image14]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAGIAAAAaCAYAAABM1ImiAAADx0lEQVR4Xu2ZS6hNURjHP6Eoz7zziqSkSJSJx00KAxLyyCMxYMAARUlcycBEQpLUTQYKhSKSwU2KKCNiQGFgQCghJY/v13fWOeuse/Y+e+9z7jm6d//q3+mste/Za3//tb71rX1FcnJycnJyugejVENUPcKOBtBbNaLw2W2ZrHqoeqI6pOpX3t0QmAQnVH9Ul1Vjyru7PlNVH1Wvww4PZuk41aCwIwN9VRMletUtVH1RPVMND/q6NPtUfwufIStVv1SbxQI3UHVP9ULSzdjtqs9i90HtEr/qLohdtzTs+F9hhraoVnlarhrqXVONOCMeiaWrwV4bM5b00eq1VYOgu/zf5YyYpXonNuhzBdXbCAJ+VdXLa5ui+iRmUBYaagQ36RM21omeqr2qlxKdZ9MQZwTtBMWHTfWt6mvQnpRON+KK2CazSCxAk1TvVXfFbnpStb54dTYmiFU3/Ha9cEbsDjsk3gj6spDEiPOS0Qhy32+xzc2BGW1iy3ux6o5YIH3SrpptqqNhYw2w+d4Xm0Azgj5olhHLxOJJGZsKqgICTWnm42bbftUpKaUScjjtrJI0MFM2iQUjSkkORYyDgxsl4ivV/PLuIs0ygvFtVP1QzZWEZTOziuqC2RpCKuLGmES97vNctSJoqwZBoQxkk44Svzvd/UEEPNgZsdS5WmzfqUSzjIABqgOqN6pdEj3GIjNV38UGGEKO48a3ww7pWBYmoUV1XTquvKww806LjXFt0Ae035LyFIrJbNQYnoUkRrSKXbcjaI9ltJhrYVB5yJ1SeVZRDpKWuIaS86JYqqgGBtxQbQg7aiCuauLgFk4Yd47AQCANHhTLCklIYgTx4rpUmzXBPCKWy3yov0lJrJZ21TrVtEIf5hHMLarZYrmf3J6E8WLB2Rp2ZCTOiD1im+aawneC3ib2SsSlWrdC+A3SdBzuQEflF3cyz2QEMFPZWChh+RE2QALsav6fqptSGugc1SUp5fK05ehIMaOpxhJtZDHEGUHgjok9G9Uaq/GDaoF3DTObZ2GVVErP4FJ0JVVaGZmNAPKoq1zCspRg+ZsNNTumYdgSrz0NrMSzYi/rvknpwXg3FK7OOOKMcIwVS6HzJLoiI31FGZGWmoxICinIvenk4ZnZw6T8NUIjSWJENZgUx8PGGmiIEVRZbILAweWB2Hv4ZsEYeOjUhycPDrKk3nrgDpnsrcSq0yBF9fe+kyMr5clGwb0xATPYs8K0mgT+sUTdXyuM5bHYWCgUWGndCiYHxQUl6DWpT1DTgplPVYclffGSk5NTxj/dhuduRmhwXAAAAABJRU5ErkJggg==>

[image15]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADwAAAAaCAYAAADrCT9ZAAACDElEQVR4Xu2XQUhUURSG/8igzLJEkFCCokUi1KJFICouBBNzpYsiaBe2cSUktAqiRdDKXLgQxIUr3QRFIkK1KnBdbQRbuahFEBRRVP4/Z97w3pm5QzMwM/K4H3wwc+69cz333XvuE4hEIpFIpBGcpf30lG/IG5P0Nz1U+N5Ot2hPsUeOUHLv6LaLj9AHLpYLlNhfuu7ivbBFOO3iQdroUR88gMzRf3TFxc/Qb/Syi2dYo1/pKOw8XKB7dBO2APP0VrF39Ryn43SqClWEkrNZDiUaSljxCRcvcoT+gRWABE20DNsy1+gGPZdqFxp32MVCHKiE78ISOubiyZa5T58iO/kv+p52pmKNpqaEk0o37RtgW1gDtRh9rk1bfBWVn0C9qSnhK/Q7rJNHAzTwpW+Ane8BH6yAFuwL7Pf+1+e0VYMDjMH6vXBxFavg7uumn1BawvXkZlB+BUXygxfpIh3OtDaGLvoR5e/hBQR2n4IP6aCL627TVtbTf01v0kuFNo1R+1V6h16HrXYzmIUV3AQV0mWUHsEMKlY/YFeTnuYOLBlV4Hv0J2x76bwL7YY39DYs+ZOwiZqB5n1MH9Eb9Bn9nOkRQC8aOsfSv3TohTx9/eiMaGF2YRM1K9k0usZUZIdQh79nibbACt4Heh6ld3Ru0FvXq8Jn/Ufylj5BoEDkhROpz9o+HanvkUikcewD8KNrS7jKGgYAAAAASUVORK5CYII=>

[image16]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADcAAAAaCAYAAAAT6cSuAAAB8ElEQVR4Xu2XyytEcRTHj1BEHnmUsLCgLCQUGzuUEitFsVAW/gShLJR/wAKJsLGSnbKQJgt5lJWdLGwoFrJgI/H99rvGvefeeZjHnTHdT32a5pw7M79z7/k9RiQgICAgzZToQK5QBPd0MIsohM2wE1aoXFQa4Bb8hF/wBbY5rsgsA3AK5lnva+CVmIKjMgTfxFzcCkdhu/x+UaYphkewWsVn4KCKuXgWU1yXTmQJHBfHx2ljZxiuqJgLtuG2ZM+T0kyIGaOGRYdgqYo74AeXdTAJesS0drzGmtt8OpGKu4d1OmHnQsxC8ijmS+ad6T+T6uJ2JYnibuESXIUbsMWZDtMnpkX8bt9NSbC4bstYlMEzuAYLVC7dzEoCxXEZfdDBFLAuZjDxOmc+FpFe+CHu0xNXy22J0Em8I0866EE5PIAnsErl/IC/fw4rVZz73LiKhWGSd65JJ2zwrvAmcHPn3MzUXjgJx2zvWfCp9epJLbwWU+ClmMesjzM8w7F9R+AdrHemfYPjeoWLYhY1jvfGcYUHXCh+zpP03YppuA8eivuU4CeNYrYOFscOynemY8P2Oxb35OWq1K9i/wIOmqsOD8sdYvpbk8mWTAr2M+cb//KExHtp3Rf/97e0wQIX4I6YJzbtyOYAXDy4+0c9dQf4zDcB92CVaj5SdgAAAABJRU5ErkJggg==>

[image17]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABEAAAAbCAYAAACa9mScAAAA7klEQVR4XmNgGAWjYKgDZiAWA2JGdAliAEhzDhC/BeJDQHwBiOVRVBABYoD4NhCrQvlHgHgSQpo4cAKIlzIgvPEfiBvgskSC5QwQjTDsiSoNB+ZA/A6I/dAlQIAbiAuB+BIQ/wXiq0AsgqKCAFADYmckvhADJIA1kcTwAhYGiFfmoImDwogfTWwxAyTAGxnQkgDMEBkkMTMgDkbigwAo7bACcToQHwBiHhRZKBAGYkkojSuhCQLxaQaIQWQDfSB+CMSm6BKkgGgGMmINHcyHYlzeJQqAwgPkGpKBOhA/AeKZDLhTMVFAAIjF0QWpCgCdmSIWFyKOtgAAAABJRU5ErkJggg==>

[image18]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAaCAYAAAC6nQw6AAABJ0lEQVR4Xu2TvUoDURBGR9BCEFEi/uADWClCEBG0t4kvEIR0NopgI1oI2vsIYmEhiLW1hWBhYRUsVAg+gF2KKKhnMrtkdhJWI1iZA6f57uXembuzIj16/CeGsBDDn1LBOm5iX+InVnGste179JALHHBZAy+x32W5DOIHroZcK9oJmV60hXMhb7KENZx2mbb2jssuUxbxFddC3mQX90O2IF22pejpeliKVrMXMuUMb/BQbE8b49J6aH2vA7H38W3pHl3fwGuxEenILb7hCx7hM0649VmxKk4TO1YUKYqNQ3yfUbwTq6qNY7E2UibFhvDBZSllyRnQc7EZmsIVvMcnnPebEnLbGsZtsZtOsCTZ6fZoW1rVr9Cf9wrX8RFnssvdMSLZL/h3fAEMUC71qY8qvAAAAABJRU5ErkJggg==>

[image19]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAHAAAAAaCAYAAABvj9h3AAAEq0lEQVR4Xu2ZXagVVRTHV2ihFlaafdmHfYBYYEVFJBEiFUVlokFGkIIP+uBTYlEE+dJD9JSEQRhSIUH2+ZBIRFwp1KyXoAiC4BRlZFQUJFb0sX6sWd191pkzs2fOubeH5gd/7j17z+wzs9fHXnsfkY6Ojo6Ojo5xcUqh6eBE1amxsaM916j2qy6MHVMExtut2hw7/q8sUe1QPav6qtAbxWe0XXWLmOdHMN7nqutiRwET7eO4GPuu9KIWzFcdVJ0QO/4jmJsLVKfFjhpmqM5RXV/8HYnbVD3VwtDOJD2t+ls1M/Rh7ItCW+QRsXs/jB0jwrNMyPSl7jLWqP5QrRebJ7LDO6rPVOdNXlbKVaplyWfu/1W1MmlrxOOqt1SzYofykJgRUi85S8ywVVHAWIzJvUTyuPlddWtsHELdhLbhkJhjnp603aT6S7UtaYswZ7tio/JKoRgotZws5jkYKsJgDIoRMJqDp/CwVRDNPbF7W3tWBZ+qXpK8F75C9YFqhVjqGgcYKk44S9IPUp1xyBoTMrgsPS9mB+zRiItV36puiB3SbwSPNvegOq92b2RsvmPcsMb2ZDDtD+My1WuqL1T3h742MCdMegpZ6kvVL6E9xYOCe+cm7YelPIhqIX2WrXEPq/5UHZB+Y7nB6/D0yfhTwZ1i46+OHZk8qPpO9ZzUr+VlVBmQvioIAuaW61yz+67IxMOZAbwKRT+q3lfdLoMp52qxBbcOjEwE1qXatniEt/LaAtLYWrFIXirVa3pkFAPCi2LP7wZ8VAbTai2esxkol1wD8lBfy/BUW1YwNcGfYxQDOjgpKewjyV8nRzHglWKFDnNwr+pnsXuekcFMWMl9Yjf2QnsV7Ft+i40lMO6wypZ0wTjOcukvknIYpwGB56H4+Fh1Segro60Bz1R9Iv3RhpNzD/OazksllL88MDduDH1V5EQgkT0sffLgLyeffbvRFF8DH4gdmVDtbVAdUb0Q+nIoc1CqXQoYKuRh4HBkpojPa7Yt/IZjqmtDXxXuZVWhTmT3ZLBCJDVRHLHOzlE9JZa6WND3qM4trmMt2itWYOyX8kLFsweHEE3hNIcC5sni/zawYR+2D2SPDDjrFrE9o8OWiveNsAtgOcuOwK1iE/CNanHoq8L3jemDp3Ai8arqdZlMExiOTTfG4jt3Fe3AS1PaOxiPs84FYmmVvp1Jv0N1ywsT7blQbfLdRF3j/VYAw2CIe4rPvCtjf6+6vGjziOSdTyra/MTm0uKz867YcWNtIZMOmor2XLbJ4MQRCXHMMuGh6QmKnwI5vDzRAbzMctUZ//ZOMqHaJ3nlN07xtlhqWyUZk5QBYzwhlsF4hzdVR8WKIIcqn8OG40kbnC12kkQfjrBbLBvkvMtYIMyzc3UFvv5xZuqwpuXsM4m+3F8lNokdujfZJuRyvupu1Y3SzDEWiTnTOrH1fNr5SXVzbGwI6ZP1lMMBFncmGMd4L7kGZ8FLU6jkYltHQzjJmJDRfmClfD6oekwmx/Hf/ChSKGKIyDS1YGQKoVG+t0MsXfjvfE1SR4R758VGsSgr21DzM07VYXFHA5h8ouGO2DFFkGqpSCkCOjo6OqaZfwC/zP+KlDjIHgAAAABJRU5ErkJggg==>

[image20]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAZCAYAAADe1WXtAAAAaklEQVR4XmNgGAWjYBQMLOAH4s1ArIkuQSkoh2KqAjEg3o8uSA1gBsQq6ILIgAeIJcnAj4A4CYg5GagEuIG4j4GKBrIA8VQgZkSXoAS4AvFqdEFKAMiVC4HYA12CEsAKxEIMVPb6KBgAAABENAjYKGAerwAAAABJRU5ErkJggg==>