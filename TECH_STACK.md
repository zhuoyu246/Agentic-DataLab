# Agentic-DataLab 技术栈详解

## 📦 本次新增的认证系统技术

### 后端新增
1. **用户认证模块**
   - passlib[bcrypt] - 密码哈希加密（降级到 4.1.3 版本以兼容 passlib）
   - python-jose[cryptography] - JWT token 生成和验证
   - email-validator - 邮箱格式验证

2. **数据库 ORM**
   - sqlalchemy - Python SQL 工具包和 ORM
   - SQLite - 轻量级嵌入式数据库（用于用户数据存储）
   - alembic - 数据库迁移工具

3. **新增 API 路由**
   - /api/v1/auth/register - 用户注册
   - /api/v1/auth/login - 用户登录
   - /api/v1/auth/me - 获取当前用户信息

### 前端新增
1. **路由管理**
   - vue-router 4.6.4 - Vue 3 官方路由库
   - 路由守卫 - 自动登录拦截和重定向

2. **状态管理**
   - Pinia Store (useAuthStore) - 用户认证状态管理
   - localStorage - Token 持久化存储

3. **HTTP 客户端增强**
   - axios 1.18.0 - HTTP 请求库
   - JWT Token 自动注入拦截器
   - 401 错误自动处理和登出

---

## 🏗️ 原有项目完整技术栈

### 核心架构
- **多智能体编排**: LangGraph 0.2.60+ (状态机架构)
- **后端框架**: FastAPI 0.115.0+ (异步 ASGI)
- **前端框架**: Vue 3.5.13 + Vite 6.0.1
- **实时通信**: Server-Sent Events (SSE) + WebSocket

### 后端技术栈

#### 核心框架
- FastAPI - 现代化异步 Web 框架
- Uvicorn - ASGI 服务器
- Pydantic 2.8+ - 数据验证和设置管理

#### AI/LLM 相关
- LangGraph 0.2.60+ - 多智能体状态机编排
- LangChain Core 0.3.0+ - LLM 应用开发框架
- Redis 5.0+ - 状态检查点持久化和缓存

#### 数据科学 & ML
- Pandas 2.2.0+ - 数据处理
- NumPy 1.26.0+ - 数值计算
- Scikit-learn 1.5.0+ - 机器学习
- MLflow 2.14.0+ - 模型训练和实验追踪
- H2O 3.46.0+ - AutoML 平台
- Plotly 5.22.0+ - 数据可视化

#### 数据库 & 存储
- SQLAlchemy 2.0+ - Python ORM
- PostgreSQL (psycopg2-binary 2.9.9+) - 关系型数据库
- SQLite - 轻量级嵌入式数据库（用户认证）
- PyArrow 16.0+ - 高性能列式存储

#### 安全 & 认证 (新增)
- Passlib 1.7.4 + bcrypt 4.1.3 - 密码加密
- python-jose 3.3.0+ - JWT 处理
- email-validator - 邮箱验证

### 前端技术栈

#### 核心框架
- Vue 3 3.5.13 - 渐进式 JavaScript 框架
- Vite 6.0.1 - 新一代前端构建工具
- TypeScript 5.6.3 - 类型安全

#### UI & 可视化
- @vue-flow/core 1.42.5+ - 流程图和管道可视化
- Plotly.js 3.6.0+ - 交互式数据图表
- Lucide Vue Next 0.468.0+ - 图标库

#### 状态 & 路由
- Pinia 2.2.6 - Vue 3 官方状态管理
- Vue Router 4.6.4 - Vue 3 官方路由 (新增)
- Axios 1.18.0 - HTTP 客户端 (新增)

---

## 🔄 认证技术实现

### JWT 认证流程
1. 用户登录 -> 后端验证 -> 生成 JWT token
2. 前端存储 token (localStorage)
3. 每次请求自动注入 Bearer token
4. 后端验证 token -> 返回用户信息
5. Token 过期或 401 -> 自动跳转登录页

### 密码安全
- bcrypt 加密算法 (cost factor = 12)
- 密码最小长度 6 位
- 用户名唯一性约束
- 邮箱格式验证

---

*更新时间: 2026-06-18*
*版本: v1.0.0 (新增认证系统)*
