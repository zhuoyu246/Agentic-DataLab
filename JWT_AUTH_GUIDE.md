# JWT 认证系统安装和使用指南

## 后端配置

### 1. 安装依赖
```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置数据库
在 `.env` 文件中配置 PostgreSQL 连接：
```env
POSTGRES_DSN=postgresql://用户名:密码@localhost:5432/数据库名
JWT_SECRET_KEY=请修改为至少32位的随机密钥
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080
```

### 3. 创建 PostgreSQL 数据库
```bash
# 登录 PostgreSQL
psql -U postgres

# 创建数据库
CREATE DATABASE agentic_datalab;

# 退出
\q
```

### 4. 初始化数据库表
```bash
cd backend
python init_db.py
```

### 5. 启动后端服务
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 前端配置

### 1. 安装依赖
```bash
cd frontend
npm install
# 或
pnpm install
```

### 2. 配置环境变量（可选）
创建 `.env` 文件：
```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 3. 启动前端服务
```bash
npm run dev
# 或
pnpm dev
```

## API 端点

### 认证相关
- `POST /api/v1/auth/register` - 用户注册
- `POST /api/v1/auth/login` - 用户登录
- `GET /api/v1/auth/me` - 获取当前用户信息（需要认证）

### 其他 API
所有其他 API 端点现在都需要在请求头中携带 JWT Token：
```
Authorization: Bearer <your_token>
```

## 用户权限

系统支持两种用户角色：
- **普通用户** (`is_admin=false`)：可以访问基本功能
- **管理员** (`is_admin=true`)：具有完整权限

## 前端页面

- `/login` - 登录页面
- `/register` - 注册页面
- `/` - 主页面（需要登录）

## 数据库表结构

### users 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| username | VARCHAR(50) | 用户名（唯一） |
| email | VARCHAR(100) | 邮箱（唯一） |
| hashed_password | VARCHAR(255) | 加密后的密码 |
| is_active | BOOLEAN | 是否激活 |
| is_admin | BOOLEAN | 是否为管理员 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

## 安全注意事项

1. **生产环境必须修改** `JWT_SECRET_KEY` 为强随机密钥
2. 建议使用 HTTPS 协议
3. 定期更新依赖包
4. 合理设置 Token 过期时间
5. 实施访问日志和监控

## 故障排查

### 前端无法连接后端
- 检查后端是否正常运行
- 检查 CORS 配置
- 检查防火墙设置

### 登录失败
- 检查用户名和密码是否正确
- 检查数据库连接是否正常
- 查看后端日志

### Token 失效
- Token 默认有效期为 7 天
- 重新登录即可获取新 Token
- 前端会自动跳转到登录页面
