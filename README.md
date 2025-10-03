# 每日基金 Home Assistant 集成

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

这是一个 Home Assistant 自定义集成，用于跟踪您的基金投资情况。通过对接天天基金网 API，实时获取基金估值数据，并在 Home Assistant 中展示详细的基金信息。

## 功能特点

- 📊 **实时基金数据** - 获取基金的实时估算净值和官方净值
- 💰 **收益计算** - 自动计算持仓收益、收益率和市值
- 📈 **趋势指示** - 通过涨跌图标直观显示基金走势
- 🕒 **定时更新** - 可配置的更新间隔，确保数据及时性
- 🔍 **详细分类** - 数据按基础数据、净值数据和估算数据分类展示

## 安装方法
### 方法一：通过 HACS 安装（推荐）
1. 确保已安装 [HACS](https://hacs.xyz/)
2. 在 HACS 的 "Integrations" 页面，点击右上角的三个点菜单，选择 "Custom repositories"
3. 在弹出窗口中添加仓库地址：https://github.com/lambilly/hass_daily_fund/ ，类别选择 "Integration"
4. 在 HACS 中搜索 "每日基金"
5. 点击下载
6. 重启 Home Assistant

### 方法二：手动安装
1. 下载本集成文件
2. 将 `custom_components/daily_fund` 文件夹复制到您的 Home Assistant 配置目录中的 `custom_components` 文件夹内
3. 重启 Home Assistant

## 配置

1. 在 Home Assistant 的「集成」页面，点击「添加集成」
2. 搜索「每日基金」
3. 按照提示填写以下信息：
   - **基金代码**：6位数字基金代码（如：012889）
   - **基金名称**：基金显示名称
   - **平均净值**：您的持仓平均净值（可选）
   - **持仓份额**：您持有的基金份额（可选）
   - **初始成本**：您的初始投资成本（可选）
   - **更新间隔**：数据更新频率，默认600秒（可选）

## 实体属性

每个基金实体包含以下分类数据：

### 基础数据
- 基金代码、基金名称、基金全称
- 涨跌净值、涨跌图标
- 平均净值、持仓份额、初始成本

### 净值数据
- 净值日期、单位净值
- 持仓市值、持仓收益、持仓收益率

### 估算数据
- 估算时间、估算净值、估算增长率
- 估算市值、估算收益、估算收益率

## 支持

如果您遇到任何问题或有建议，请通过以下方式联系：

- [提交 Issue](https://github.com/lambilly/daily_fund/issues)
- [查看文档](https://github.com/lambilly/daily_fund)

## 许可证

MIT License
