import os
import re

views_dir = '/home/wppjkw/smartphoto_backend/adminfront/src/views/'

replacements = {
    r'<span class="eyebrow">Audit</span>': r'<span class="eyebrow">审计记录</span>',
    r'<span class="eyebrow">Audit Detail</span>': r'<span class="eyebrow">审计追踪详情</span>',
    r'<h4>Before Snapshot</h4>': r'<h4>变更前快照代码</h4>',
    r'<h4>After Snapshot</h4>': r'<h4>变更后快照代码</h4>',
    
    r'<span class="eyebrow">System</span>': r'<span class="eyebrow">系统观测</span>',
    
    r'<span class="eyebrow">Prompts</span>': r'<span class="eyebrow">提示词模板管理</span>',
    r'<span class="eyebrow">Prompt Preset Editor</span>': r'<span class="eyebrow">Prompt Preset 编辑器</span>',
    r'<th>Prompt Preset</th>': r'<th>Prompt预设</th>',
    r'<th>Category/Platform</th>': r'<th>品类 / 平台</th>',
    
    r'<span class="eyebrow">Category Catalog</span>': r'<span class="eyebrow">品类库管理</span>',
    r'<span class="eyebrow">Catalog Editor</span>': r'<span class="eyebrow">品类库编辑器</span>',
    
    r'<span class="eyebrow">Assets</span>': r'<span class="eyebrow">素材资产库</span>',
    r'<span class="eyebrow">Asset Preview</span>': r'<span class="eyebrow">素材大图预览</span>',
    
    r'<span class="eyebrow">Jobs</span>': r'<span class="eyebrow">任务队列管理</span>',
    r'<span class="eyebrow">Job Detail</span>': r'<span class="eyebrow">任务执行详情</span>',
    r'<h4>Events Timeline</h4>': r'<h4>事件流时间轴</h4>',
    r'<th>Job</th>': r'<th>任务 ID</th>',
    r'<th>Type</th>': r'<th>执行类型</th>',
    
    r'<span class="eyebrow">Sessions</span>': r'<span class="eyebrow">会话追踪干预</span>',
    r'<span class="eyebrow">Session Control</span>': r'<span class="eyebrow">多轮会话干预控制面</span>',
    
    r'<span class="eyebrow">Overview</span>': r'<span class="eyebrow">全局概览</span>',
    r'<h4>Recent Activity</h4>': r'<h4>最近高危活动</h4>',
    
    r'<th>Version</th>': r'<th>版本信息</th>',
    r'<th>Status</th>': r'<th>状态</th>',
    r'<th>Target</th>': r'<th>审计目标</th>',
    r'<th>Result</th>': r'<th>处理结果</th>',
    r'<th>Created</th>': r'<th>创建时间</th>',
    
    r'>Refresh<': r'>刷新<',
    r'>Archive<': r'>归档禁用<',
    r'>Clone<': r'>克隆<',
    r'>Publish<': r'>发布版本<',
    r'>Restore<': r'>恢复启用<',
    r'>Save<': r'>保存<',
    r'>Retry<': r'>重试<',
    r'>View<': r'>查看详情<'
}

for root, dirs, files in os.walk(views_dir):
    for file in files:
        if file.endswith('.vue'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            original = content
            for p, r in replacements.items():
                content = re.sub(p, r, content, flags=re.IGNORECASE)
            if content != original:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"Updated {file}")
