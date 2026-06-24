# Research Report: State of Agentic Harnesses and Orchestration Loops

## Executive Summary

The paradigm of large language model (LLM) agents is executing a fundamental shift in 2025 and 2026, transitioning from static, hand-engineered orchestrators to dynamic, self-evolving, and structure-aware agentic harnesses. Historically, the harness was treated as a rigid wrapper responsible for managing system prompts, basic API call loops, and isolated tool executions. However, recent literature establishes that a harness must act as an intelligent mediator capable of autonomous evolution. Through paradigms like Agentic Harness Engineering (AHE) and open-ended program optimization, harnesses can iteratively refine their own tool configurations, middleware, and decision boundaries without human intervention. At the same time, the physical and spatial limits of foundation models are being redressed using spatial-cognitive map priors—such as allocentric global representations translated from local egocentric views—while real-time, interactive environment interfaces like Unreal Engine 5 are deploying "improvement dynamics" harnesses to evaluate and autonomously escalate agent capabilities.

This rapid expansion in complexity introduces corresponding challenges in memory management, evaluation, and security. Agentic memory is moving away from basic vector retrieval towards mathematically structured Partially Observable Markov Decision Processes (POMDPs) and query-conditioned relational graphs, ensuring that context windows do not decay into lossy representations during complex, multi-hop search operations. Concurrently, the operational capabilities of modern harnesses (such as local file modification, tool persistence, and cross-session memory reuse) have exposed major security vulnerabilities. Multi-step trojan backdoors are now capable of embedding persistent control in local agent environments through discrete, seemingly benign steps, necessitating runtime tracking defenses that trace file-origin verification. Collectively, these advancements underscore a new era where agentic harnesses are no longer passive execution wrappers but are robust, self-defending, and evolving cognitive systems.

## Core Emerging Themes

### Theme 1: Autonomous Harness Evolution and Self-Refinement via Reinforcement Learning
A major trend across current research is the programmatic and evolutionary development of harnesses, shifting away from manual prompts and static middleware loops. Instead of human engineers anticipating every action space and failure mode, frameworks like Agentic Harness Engineering (AHE), ShinkaEvolve, and OmniGameArena employ LLMs and reinforcement learning (RL) to evolve coding-agent tool-use architectures and game-strategy inputs autonomously. This evolution relies on structural observability pillars: tracking discrete harness components as code, distilling raw token trajectories into drill-down evidence, and validating edits against strict task outcomes. Relatedly, models are beginning to internalize multi-step reasoning architectures ("heavy thinking") as parametrized inner skills via reinforcement learning, moving past brittle, top-down orchestration prompts by directly training models to balance exploration and exploitation inside the loop.

### Theme 2: Transition from Flat Vector Retrieval to Structured Cognitive Mapping and Mathematical Search
As LLM agents are deployed in high-density domains and complex environments, memory retrieval has shifted away from static vector lookups toward structured relational representations. To navigate environments where context size dwarfs LLM context limits, developers are formalizing search execution processes as Partially Observable Markov Decision Processes (POMDPs) using programmatic belief updates and exhaustion gates to prevent redundant looping. In spatial and physical domains, this structured mapping takes the form of translating noisy egocentric observations into allocentric maps (e.g., Allocentric-Spatial Trees), providing agents with persistent geometric, relational, and topological priors. Architectures such as HAGE further enhance this dynamic by utilizing RL to weight multi-relational graphs, enabling query-conditioned traversal where edge feature vectors adapt dynamically to the agent's current intent.

### Theme 3: Multi-Step Evaluation, Error Taxonomy, and Workspace Security Defenses
With local harnesses capable of executing complex tool chains, reading and writing code, and persistently caching workspace state across multiple cycles, security and validation paradigms have had to radically evolve. The emergence of multi-step trojan attacks (such as ClawTrojan) demonstrates that attackers can bypass traditional single-turn prompt-injection defenses by splitting a malicious instruction across safe intermediate file-write actions. This requires the integration of defense layers like DASGuard, which scan, trace, and sanitize unauthorized file modifications back to trusted sources. In tandem, traditional accuracy and factuality scoring are struggling to capture failures in long-form, multi-tool outputs. Researchers are therefore building dedicated error taxonomies (such as those in DeFi analysis) and deploying programmatic, cite-verifiable LLM judge rubrics to handle the complex, real-world context sizes handled by modern agentic architectures.

## Annotated Bibliography of 10 Pioneer Papers

**[ShinkaEvolve: Towards Open-Ended And Sample-Efficient Program Evolution]**  
*Authors:* Robert Tjarko Lange, Yuki Imajuku, Edoardo Cetin  
*URL:* https://arxiv.org/abs/2509.19349  
*Summary:* This work introduces ShinkaEvolve, an open-source evolutionary computation framework that uses LLMs as mutation operators to adaptively optimize and generate high-performing agentic harnesses. By incorporating novelty rejection-sampling and a bandit-based LLM ensemble, it achieves remarkable sample efficiency in synthesizing complex agent behaviors.

**[CryptoAnalystBench: Failures in Multi-Tool Long-Form LLM Analysis]**  
*Authors:* Anushri Eswaran, Oleg Golev, Darshan Tank, Sidhant Rahi, Himanshu Tyagi  
*URL:* https://arxiv.org/abs/2602.11304  
*Summary:* This paper introduces CryptoAnalystBench to analyze the reliability of multi-tool agentic harnesses under high-density data constraints in the decentralized finance domain. It designs an evaluation pipeline that incorporates citation verification and structural judge rubrics to expose critical higher-order agent planning and failure modes.

**[Agentic Harness Engineering: Observability-Driven Automatic Evolution of Coding-Agent Harnesses]**  
*Authors:* Jiahang Lin, Shichun Liu, Chengjun Pan, Lizhi Lin, Shihan Dou, Xuanjing Huang, Hang Yan, Zhenhua Han, Tao Gui  
*URL:* https://arxiv.org/abs/2604.25850  
*Summary:* The paper presents Agentic Harness Engineering (AHE), an observability-driven closed loop that automates the optimization of coding-agent harnesses autonomously. By structuring the harness into explicit components, experience corpora, and decision-tracking layers, it mitigates trial-and-error failures and generates generalizable, high-value tool-use middleware.

**[HeavySkill: Heavy Thinking as the Inner Skill in Agentic Harness]**  
*Authors:* Jianing Wang, Linsen Guo, Zhengyu Chen, Qi Guo, Hongyu Zang, Wenjie Shi, Haoxiang Ma, Xiangyu Xi, Xiaoyu Li, Wei Wang, Xunliang Cai  
*URL:* https://arxiv.org/abs/2605.02396  
*Summary:* This paper introduces HeavySkill, a framework that conceptualizes "heavy thinking" as an intrinsic, RL-scalable inner skill of a model rather than a static feature of a brittle orchestration layer. It structures a two-step parallel reasoning and summarization harness that allows agents to internalize and scale complex execution workflows.

**[The Context Gathering Decision Process: A POMDP Framework for Agentic Search]**  
*Authors:* Chinmaya Kausik, Adith Swaminathan, Nathan Kallus  
*URL:* https://arxiv.org/abs/2605.07042  
*Summary:* This paper formalizes iterative search as a Partially Observable Markov Decision Process called the Context Gathering Decision Process (CGDP) to prevent memory degradation in agentic harnesses. It introduces a programmatic belief-state tracker and an exhaustion gate to replace lossy implicit working memories with structured, non-interfering search controllers.

**[HAGE: Harnessing Agentic Memory via RL-Driven Weighted Graph Evolution]**  
*Authors:* Dongming Jiang, Yi Li, Guanpeng Li, Qiannan Li, Bingzhe Li  
*URL:* https://arxiv.org/abs/2605.09942  
*Summary:* The authors propose HAGE, a memory retrieval harness that transitions agentic memory away from static lookup tables to dynamic, query-conditioned traversals of weighted multi-relational graphs. By integrating reinforcement learning to fine-tune routing behaviors and edge weights, HAGE optimizes complex long-horizon reasoning trajectories.

**[From Prompt Injection to Persistent Control: Defending Agentic Harness Against Trojan Backdoors]**  
*Authors:* Jiejun Tan, Zhicheng Dou, Xinyu Yang, Yuyang Hu, Yiruo Cheng, Xiaoxi Li, Ji-Rong Wen  
*URL:* https://arxiv.org/abs/2605.31042  
*Summary:* This study introduces ClawTrojan and DASGuard to define and mitigate multi-step trojan attacks that exploit the persistent file-writing and tool-call persistence of local agentic harnesses. DASGuard provides defense by dynamically inspecting context, tracing local file modifications back to trusted sources, and running sanitized workspace commits.

**[DAR: Deontic Reasoning with Agentic Harnesses]**  
*Authors:* Guangyao Dou, William Jurayj, Nils Holzenberger, Benjamin Van Durme  
*URL:* https://arxiv.org/abs/2606.05009  
*Summary:* The paper evaluates Deontic Agentic Reasoning (DAR), a setup testing agentic harnesses and interactive statutory rule retrieval on complex regulatory reasoning tasks. It demonstrates how dynamic statutory consultation helps scale rule-following agents but exposes trade-offs where weaker models struggle with tool-use overhead.

**[AlloSpatial: Agentic Harness Framework for Spatial Reasoning in Foundation Models]**  
*Authors:* Shouwei Ruan, Bin Wang, Zhenyu Wu, Qihui Zhu, Yuxiang Zhang, Jingzhi Li, Yubin Wang, Xingxing Wei  
*URL:* https://arxiv.org/abs/2606.08952  
*Summary:* This paper introduces AlloSpatial, an agentic harness that tackles spatial-cognitive limitations in multimodal models by constructing World2Mind allocentric spatial-tree priors from egocentric perspectives. It couples these structured memory priors with a specialized Spatial Reasoning Harness to arbitrate noisy sensor feeds and guide complex geometric planning.

**[OmniGameArena: A Unified UE5 Benchmark for VLM Game Agents with Improvement Dynamics]**  
*Authors:* Mingxian Lin, Shengju Qian, Yuqi Liu, Yi-Hua Huang, Yiyu Wang, Wei Huang, Yitang Li, Fan Zhang, Zeyu Hu, Lingting Zhu, Xin Wang, Xiaojuan Qi  
*URL:* https://arxiv.org/abs/2606.09826  
*Summary:* This paper presents OmniGameArena, a multi-game UE5 benchmark evaluating VLM agents through a novel agentic-reflection harness called the Improvement Dynamics Curve (IDC). The IDC framework enables an autonomous reflector LLM to iteratively adapt, test, and optimize an agent's capability bounds across multi-round scenarios.