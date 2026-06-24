# Paddle（MoR）卖家入驻 — 材料准备清单

> **适用场景**：大陆个人独立开发者、无公司主体，通过 Paddle 向美东（及全球）客户销售 FastDoc SaaS 订阅；客户可使用 Visa、Mastercard 等信用卡支付。  
> **关联项目**：`fast-doc`（API + Webhook）、`fast-doc-app`（定价页 + 法律页 + Checkout 入口）、`fast-doc-extension`（订阅鉴权）。  
> **最后更新**：2026-05-22

---

## 1. 背景与约束

| 项目 | 说明 |
|------|------|
| 卖家身份 | 个人 / Sole trader（无公司执照通常即可） |
| 客户地区 | 美国东海岸为主，定价 **USD** |
| 支付方式 | Paddle Checkout：Visa、Mastercard、Amex 等（由 Paddle 托管，卡号不进自有服务器） |
| 大陆限制 | 无法直接开通 Stripe；Lemon Squeezy 不支持大陆卖家提现 |
| 美国银行卡 | **卖家不需要**；需配置 Paddle 支持的**提现账户**（银行电汇 / Payoneer 等，以后台为准） |

**MoR 含义**：Paddle 作为 Merchant of Record 代收税款、开发票、处理退款；你提供软件与 Webhook 同步订阅状态。

---

## 2. 审核流程概览

Paddle Live 账户通常需完成三步（个人卖家一般**不需要**公司注册文件）：

```
注册 Sandbox → 准备网站与法律页 → 域名审核（DNS TXT）
    → 身份验证（Onfido：证件 + 自拍）
    → 配置 Payout → 创建 Product/Price → 接入 Checkout + Webhook
```

| 阶段 | 大约时间 |
|------|----------|
| Sandbox 注册 | 当天 |
| 域名 + 网站内容审核 | 约 2–10 天（多数几天内） |
| Onfido 身份验证 | 多数即时；人工复核约 1–3 工作日 |
| 全部通过后开启 Live 收款 | 视补料情况而定 |

**建议**：网站与法律页先上线，再提交 Domain approval；同时用 Sandbox 开发集成，避免空等。

**官方参考**：

- [注册要点](https://paddle.com/help/start/intro-to-paddle/essentials-to-sign-upcreate-a-paddle-account)
- [域名审核](https://paddle.com/help/start/account-verification/what-is-domain-verification)
- [身份验证](https://paddle.com/help/start/account-verification/what-is-identity-verification)
- [企业验证](https://paddle.com/help/start/account-verification/what-is-business-verification)（个人通常无需额外材料）
- [Acceptable Use Policy](https://paddle.com/help/start/intro-to-paddle/what-am-i-not-allowed-to-sell-on-paddle)
- [Seller Handbook](https://www.paddle.com/seller-guides/seller-handbook)
- [开发者 Setup Checklist](https://developer.paddle.com/build/set-up-checklist)

---

## 3. 材料清单（按类别）

### 3.1 个人身份（必做）

| 项目 | 说明 |
|------|------|
| 真实姓名、国籍、常住地址 | 与证件一致 |
| 政府证件 | **护照**或身份证（Onfido 支持列表内的**原件**拍照） |
| 人脸识别 | 邮件中的 Onfido 链接：证件照片 + 短视频自拍 |
| 邮箱、手机 | 可接收验证信息 |

个人/个体户：**只验证本人**；一般不需要营业执照、股东名册（注册公司时才可能需要）。

---

### 3.2 网站与域名（必做，最易卡审）

#### 网站必须满足

- [ ] 已部署且可公网访问（`localhost` 无法通过域名审核）
- [ ] **HTTPS**（有效 SSL 证书）
- [ ] 导航或页脚可访问：**产品说明、定价、Terms、Privacy、Refund**
- [ ] 公开 **支持/联系邮箱**（如 `support@yourdomain.com`）

#### 建议页面与内容（英文，面向美国客户）

| 路径/区域 | 建议包含 |
|-----------|----------|
| 首页 / 产品 | FastDoc：临床文档、语音转写、SOAP/EMR 工作流；强调为 **software tool**，非诊疗建议 |
| 定价 | 与产品一致，例如 Starter $49/月、Professional $99/月、14-day trial |
| `/terms` | 订阅周期、自动续费、取消方式、责任限制、知识产权、服务变更 |
| `/privacy` | 收集的数据类型、用途、存储、用户权利；如涉及医疗数据需如实表述 |
| `/refund` | 退款窗口、申请方式、与 Paddle 处理的关系 |

#### Paddle 强制文案（写入网站 Terms of Service）

Paddle 要求说明结账由 Paddle 作为 reseller 处理，示例：

> Payments for our software are processed by Paddle.com Market Ltd, who acts as the Merchant of Record for our products.

详见 [Seller Handbook — Policies](https://www.paddle.com/seller-guides/seller-handbook)。

#### 域名所有权验证

- [ ] 在 Paddle 后台 **Checkout → Request domain approval** 提交域名
- [ ] 在 DNS 服务商添加 **TXT** 记录：`paddle-verification=<平台提供的值>`
- [ ] 提交用于发起 Checkout 的每个域名/子域名（至少一个通过即可继续）

---

### 3.3 产品与业务信息（注册及审核表单）

| 字段 | FastDoc 建议填写 |
|------|------------------|
| 业务类型 | B2B SaaS / Medical practice software |
| 销售模式 | Subscription（月付），可选 trial |
| 币种 | USD |
| Tax category | 按 Paddle 后台下拉选择 **软件/SaaS** 对应项，勿随意归类 |
| 产品 | FastDoc Starter、FastDoc Professional 等 |
| 定价 | 与 `fast-doc-app` 落地页一致 |

#### 医疗类产品 — AUP 注意事项

Paddle **禁止**：提供 **medical advice**（诊断、治疗、用药建议等）。

**允许**：销售 **软件/SaaS**（文档、转写、工作流工具）。

审核描述建议强调：

- 销售对象为 **documentation / transcription / EMR workflow** 软件
- **不提供**诊断或治疗建议
- 结账流程 **不收集** 患者 PHI（姓名、病历等）
- 若产品需登录使用，按邮件要求提供 **测试账号**（邮箱 + 密码）

若被列为 Restricted Category，按邮件补充说明或材料即可。

---

### 3.4 收款账户（Live 通过后配置）

| 项目 | 说明 |
|------|------|
| 提现方式 | 以 Paddle 后台 **Payout** 可选列表为准（大陆常见：银行电汇、Payoneer 等） |
| 账户姓名 | 与身份验证姓名一致 |
| 最低结算额 | 通常有门槛（如 $100），以后台说明为准 |
| 疑问 | 可联系 `sellers@paddle.com`；勿伪造他国地址 |

---

### 3.5 技术准备（非 KYC，但上线前需完成）

- [ ] Paddle **Sandbox** 账号与 API Key
- [ ] 在 Paddle 创建 **Product + Price**（USD  recurring）
- [ ] `fast-doc`：`POST /v1/billing/checkout-session`（或等价）创建 Checkout
- [ ] `POST /v1/webhooks/paddle`：验签 + 幂等更新 `subscriptions` 表
- [ ] `GET /v1/auth/me` 或 `/entitlements`：返回 `active` / `trialing` / `past_due` 等
- [ ] `fast-doc-extension`：登录/刷新后校验订阅，未付费则限制核心功能
- [ ] Webhook 与结账回调 URL 为 **HTTPS** 生产地址
- [ ] 试用天数、取消规则与网站文案一致

---

## 4. 文件夹式准备包（建议本地归档）

```text
paddle-onboarding/
├── 01-identity/
│   └── 护照/身份证（Onfido 用手机拍摄即可，可自备扫描备份）
├── 02-website/                    # 对应 fast-doc-app 生产部署
│   ├── 首页 - 产品介绍
│   ├── pricing - 定价
│   ├── terms.html 或 /terms
│   ├── privacy.html 或 /privacy
│   └── refund.html 或 /refund
├── 03-dns/
│   └── 域名注册商/Cloudflare 登录方式（添加 TXT 用）
├── 04-paddle-dashboard/
│   ├── 卖家注册信息（个人）
│   ├── Product / Price 配置截图
│   └── Domain approval 提交记录
└── 05-optional/                   # 若审核要求时提供
    ├── 产品截图 + 功能列表 PDF（英文）
    └── 测试账号 credentials.txt
```

---

## 5. fast-doc-app 上线前差距（当前常见缺项）

基于仓库现状，提交 Paddle 域名审核前建议补齐：

1. [ ] 独立页面：`/terms`、`/privacy`、`/refund`（英文）
2. [ ] Terms 中包含 Paddle reseller 声明（见 §3.2）
3. [ ] 生产 **HTTPS 域名**（非仅本地开发）
4. [ ] 文案定位：**clinical documentation software**，避免 “AI 诊断 / medical advice”
5. [ ] 定价按钮流程：注册 → Checkout → Webhook 开通权限（与 Extension 鉴权闭环）

---

## 6. 客户支付体验（与 Udemy 等同类）

用户流程：

```text
fast-doc-app 选择套餐
  → 跳转 Paddle Checkout（Hosted）
  → 填写 Visa / Mastercard + 美国账单地址
  → 支付成功 → Webhook → fast-doc 更新订阅
  → Extension / Web 端获得权限
```

客户**不需要** Paddle 账号；卖家**不需要**美国银行卡。

---

## 7. 订阅与计费模型建议（实现时参考）

| 决策项 | 建议 |
|--------|------|
| 计费主体 | 订阅绑在 `provider`（诊所），非单个 user |
| 试用 | 14 天 trial（与落地页一致）；是否绑卡需在 Paddle 产品里配置 |
| Starter 限额 | 例如每月 100 encounters，与定价文案一致 |
| Enterprise | 人工开通或 Paddle Invoice，可不走自助 Checkout |

---

## 8. 大陆个人 — 税务与合规提醒

- 境外 SaaS 收入在大陆通常需按 **个人所得税** 申报（请咨询本地税务/会计）
- 支付页仅处理 **订阅费**，不收集患者信息
- 若使用加拿大朋友代收等方案，需书面协议；**不建议**无协议代开他人 Paddle/Stripe 账户

---

## 9. 检查表（提交审核前勾选）

### 身份

- [ ] Paddle 账号已注册（先 Sandbox）
- [ ] 已收到并完成 Onfido 身份验证（或等待邮件）

### 网站

- [ ] HTTPS 生产站点可访问
- [ ] Terms / Privacy / Refund 可从导航进入
- [ ] 定价与功能说明清晰
- [ ] Terms 含 Paddle MoR 声明
- [ ] 页脚有 support 邮箱
- [ ] 产品描述符合 SaaS 工具定位（非 medical advice）

### 域名

- [ ] 已在后台提交域名
- [ ] DNS TXT `paddle-verification=...` 已添加并生效

### 产品与收款

- [ ] Product / Price（USD subscription）已创建
- [ ] Payout 账户已绑定（Live 阶段）
- [ ] Sandbox Webhook 已打通 fast-doc

### 可选补料

- [ ] 测试账号已准备（登录型产品）
- [ ] 产品截图/说明 PDF（英文）

---

## 10. 相关链接

| 资源 | URL |
|------|-----|
| Paddle 注册 | https://www.paddle.com/get-started |
| 开发者文档 | https://developer.paddle.com/ |
| 支持国家（卖家） | https://paddle.com/help/start/intro-to-paddle/which-countries-are-supported-by-paddle |
| 支持支付方式 | https://paddle.com/help/start/intro-to-paddle/which-payment-methods-do-you-support |
| 试用订阅说明 | https://paddle.com/help/start/intro-to-paddle/what-are-trial-subscriptions |

---

## 11. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-22 | 初版：大陆个人开发者 + FastDoc + Paddle MoR 材料清单 |
