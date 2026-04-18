# 华为智能二手机估值系统

基于 **uni-app x** 开发的华为二手手机智能估值 App，配套 **Python Flask** 后端。支持手机基础参数录入、外观检测、功能检测、智能估值计算及估值记录管理。

---

## 功能模块

| 模块 | 说明 |
|------|------|
| 登录 / 注册 | 账号密码登录，Token 鉴权 |
| 首页 | 估值流程引导、服务亮点、门店信息 |
| 手机参数录入 | 机型（支持模糊搜索下拉选择）、内存、存储、渠道、使用时长 |
| 外观检测 | 上传图片，模拟 AI 检测外观评分 |
| 功能检测 | 电池健康度、摄像头、指纹、充电口、屏幕、扬声器 |
| 估值结果 | 自动计算回收价 / 销售参考价，保存后返回首页 |
| 估值记录 | 历史记录列表，支持搜索和再次评估 |
| 机型管理 | 华为机型增删管理 |
| 个人中心 | 用户信息、服务菜单、退出登录 |

---

## 技术栈

**前端**
- [uni-app x](https://doc.dcloud.net.cn/uni-app-x/)（`.uvue` 页面）
- Vue 3 Composition API
- 原生 uni-app 组件，无第三方 UI 库依赖
- 统一蓝色主题（`#1a56db`）

**后端**
- Python 3 + Flask
- SQLite（零配置本地数据库）
- flask-cors 跨域支持

---

## 目录结构

```
phoneRecyle/
├── pages/
│   └── phoneRecyle/
│       ├── tabBar/               # 底部导航四个页面
│       │   ├── home/             # 首页
│       │   ├── valuationRecord/  # 估值记录
│       │   ├── service/          # 服务咨询
│       │   └── profile/          # 个人中心
│       ├── login/                # 登录页
│       ├── inputParams/          # 参数录入（模糊搜索下拉）
│       ├── appearanceDetect/     # 外观检测
│       ├── functionTest/         # 功能检测
│       ├── valuationResult/      # 估值结果
│       ├── modelManage/          # 机型管理
│       └── paramConfig/          # 参数配置
├── static/
│   └── tabbar/                   # 底部导航图标（PNG）
├── backend/
│   ├── app.py                    # Flask 后端入口
│   └── requirements.txt
├── pages.json                    # 路由 & tabBar 配置
└── manifest.json
```

---

## 快速开始

### 前端

1. 安装 [HBuilderX](https://www.dcloud.io/hbuilderx.html)
2. 用 HBuilderX 打开本项目目录
3. 菜单栏：运行 → 运行到模拟器 / 真机

### 后端

```bash
cd backend
pip install -r requirements.txt
python app.py
```

后端默认运行在 `http://localhost:5000`

默认账号：`admin` / `admin123`

---

## API 接口

| 方法 | 路径 | 说明 | 需要登录 |
|------|------|------|---------|
| POST | `/api/login` | 登录，返回 token | ✗ |
| POST | `/api/register` | 注册 | ✗ |
| GET | `/api/models` | 获取机型列表 | ✗ |
| POST | `/api/models` | 添加机型 | ✓ |
| DELETE | `/api/models/:id` | 删除机型 | ✓ |
| POST | `/api/valuate` | 提交估值（自动计算价格） | ✓ |
| GET | `/api/valuations` | 获取当前用户估值记录 | ✓ |
| DELETE | `/api/valuations/:id` | 删除估值记录 | ✓ |

需要登录的接口请在请求头携带：
```
Authorization: Bearer <token>
```

---

## 估值算法

```
基础价格 × (1 - 0.018 × 使用月数) × (外观评分 / 100) × (电池健康度 / 100)

回收价       = 计算结果 × 75%
销售参考价   = 计算结果 × 88%
```

---

## License

MIT
