import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'ACE-Step 1.5',
  description: 'Open-Source Music Generation Foundation Model',

  base: '/ACE-Step-1.5/',
  lastUpdated: true,
  cleanUrls: true,
  ignoreDeadLinks: [
    /localhost/,
    /\.\.\/\.\.\/README/,
    // Missing translations
    /\.\/BENCHMARK/,
    // Links from awesome-ace-step README (external repo)
    /\.\/CONTRIBUTING/,
  ],

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/ACE-Step-1.5/favicon.svg' }],
    ['meta', { name: 'og:type', content: 'website' }],
    ['meta', { name: 'og:title', content: 'ACE-Step 1.5 Documentation' }],
    ['meta', { name: 'og:description', content: 'Open-Source Music Generation Foundation Model' }],
  ],

  locales: {
    en: {
      label: 'English',
      lang: 'en',
      link: '/en/',
      themeConfig: {
        nav: navEN(),
        sidebar: sidebarEN(),
      },
    },
    zh: {
      label: '中文',
      lang: 'zh-CN',
      link: '/zh/',
      themeConfig: {
        nav: navZH(),
        sidebar: sidebarZH(),
        outline: { label: '页面导航' },
        lastUpdated: { text: '最后更新于' },
        docFooter: { prev: '上一页', next: '下一页' },
        editLink: { pattern: 'https://github.com/ace-step/ACE-Step-1.5/edit/main/docs/:path', text: '在 GitHub 上编辑此页面' },
      },
    },
    ja: {
      label: '日本語',
      lang: 'ja',
      link: '/ja/',
      themeConfig: {
        nav: navJA(),
        sidebar: sidebarJA(),
        outline: { label: 'ページナビ' },
        lastUpdated: { text: '最終更新' },
        docFooter: { prev: '前へ', next: '次へ' },
        editLink: { pattern: 'https://github.com/ace-step/ACE-Step-1.5/edit/main/docs/:path', text: 'GitHub でこのページを編集' },
      },
    },
    ko: {
      label: '한국어',
      lang: 'ko',
      link: '/ko/',
      themeConfig: {
        nav: navKO(),
        sidebar: sidebarKO(),
        outline: { label: '페이지 탐색' },
        lastUpdated: { text: '마지막 업데이트' },
        docFooter: { prev: '이전', next: '다음' },
        editLink: { pattern: 'https://github.com/ace-step/ACE-Step-1.5/edit/main/docs/:path', text: 'GitHub에서 이 페이지 편집' },
      },
    },
  },

  themeConfig: {
    logo: '/logo.png',

    socialLinks: [
      { icon: 'github', link: 'https://github.com/ace-step/ACE-Step-1.5' },
      { icon: 'discord', link: 'https://discord.gg/PeWDxrkdj7' },
    ],

    search: {
      provider: 'local',
    },

    editLink: {
      pattern: 'https://github.com/ace-step/ACE-Step-1.5/edit/main/docs/:path',
      text: 'Edit this page on GitHub',
    },

    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright 2025-present ACE-Step Team',
    },
  },
})

// ---------------------------------------------------------------------------
// English
// ---------------------------------------------------------------------------

function navEN() {
  return [
    {
      text: 'Guide',
      items: [
        { text: 'Installation', link: '/en/INSTALL' },
        { text: 'Tutorial', link: '/en/Tutorial' },
        { text: 'Gradio UI', link: '/en/GRADIO_GUIDE' },
        { text: 'CLI', link: '/en/CLI' },
      ],
    },
    {
      text: 'API',
      items: [
        { text: 'Local API', link: '/en/API' },
        { text: 'OpenRouter API', link: '/en/Openrouter_API_DOC' },
      ],
    },
    {
      text: 'Advanced',
      items: [
        { text: 'LoRA Training', link: '/en/LoRA_Training_Tutorial' },
        { text: 'Benchmark', link: '/en/BENCHMARK' },
        { text: 'GPU Compatibility', link: '/en/GPU_COMPATIBILITY' },
      ],
    },
    {
      text: 'SideStep',
      link: '/sidestep/Getting Started',
    },
    {
      text: 'Ecosystem',
      link: '/en/awesome',
    },
  ]
}

function sidebarEN() {
  return {
    '/en/': [
      {
        text: 'Getting Started',
        items: [
          { text: 'Installation', link: '/en/INSTALL' },
          { text: 'Tutorial (Must Read)', link: '/en/Tutorial' },
        ],
      },
      {
        text: 'User Guide',
        items: [
          { text: 'Gradio UI Guide', link: '/en/GRADIO_GUIDE' },
          { text: 'CLI', link: '/en/CLI' },
          { text: 'Studio', link: '/en/studio' },
          { text: "Musician's Guide", link: '/en/ace_step_musicians_guide' },
        ],
      },
      {
        text: 'API Reference',
        items: [
          { text: 'Local API', link: '/en/API' },
          { text: 'OpenRouter API', link: '/en/Openrouter_API_DOC' },
          { text: 'Inference', link: '/en/INFERENCE' },
        ],
      },
      {
        text: 'Advanced',
        items: [
          { text: 'LoRA Training', link: '/en/LoRA_Training_Tutorial' },
          { text: 'GPU Compatibility', link: '/en/GPU_COMPATIBILITY' },
          { text: 'GPU Troubleshooting', link: '/en/GPU_TROUBLESHOOTING' },
          { text: 'Benchmark', link: '/en/BENCHMARK' },
          { text: 'ROCm on Linux', link: '/en/ACE-Step1.5-Rocm-Manual-Linux' },
        ],
      },
      {
        text: 'Ecosystem',
        items: [
          { text: 'Awesome ACE-Step', link: '/en/awesome' },
        ],
      },
    ],
    '/sidestep/': [
      {
        text: 'SideStep',
        link: 'https://github.com/koda-dernet/Side-Step',
        items: [
          { text: 'Getting Started', link: '/sidestep/Getting Started' },
          { text: 'Dataset Preparation', link: '/sidestep/Dataset Preparation' },
          { text: 'Training Guide', link: '/sidestep/Training Guide' },
          { text: 'End-to-End Tutorial', link: '/sidestep/End-to-End Tutorial' },
          { text: 'Model Management', link: '/sidestep/Model Management' },
          { text: 'Preset Management', link: '/sidestep/Preset Management' },
          { text: 'Using Your Adapter', link: '/sidestep/Using Your Adapter' },
          { text: 'Estimation Guide', link: '/sidestep/Estimation Guide' },
          { text: 'Shift & Timestep Sampling', link: '/sidestep/Shift and Timestep Sampling' },
          { text: 'The Settings Wizard', link: '/sidestep/The Settings Wizard' },
          { text: 'VRAM Optimization', link: '/sidestep/VRAM Optimization Guide' },
          { text: 'Windows Notes', link: '/sidestep/Windows Notes' },
        ],
      },
    ],
  }
}

// ---------------------------------------------------------------------------
// Chinese
// ---------------------------------------------------------------------------

function navZH() {
  return [
    {
      text: '指南',
      items: [
        { text: '安装', link: '/zh/INSTALL' },
        { text: '教程', link: '/zh/Tutorial' },
        { text: 'Gradio UI', link: '/zh/GRADIO_GUIDE' },
      ],
    },
    {
      text: 'API',
      items: [
        { text: '本地 API', link: '/zh/API' },
        { text: 'OpenRouter API', link: '/zh/Openrouter_API_DOC' },
      ],
    },
    {
      text: '进阶',
      items: [
        { text: 'LoRA 训练', link: '/zh/LoRA_Training_Tutorial' },
        { text: '评测', link: '/zh/BENCHMARK' },
        { text: 'GPU 兼容性', link: '/zh/GPU_COMPATIBILITY' },
      ],
    },
    {
      text: '生态',
      link: '/en/awesome',
    },
  ]
}

function sidebarZH() {
  return {
    '/zh/': [
      {
        text: '快速开始',
        items: [
          { text: '安装指南', link: '/zh/INSTALL' },
          { text: '教程 (必读)', link: '/zh/Tutorial' },
        ],
      },
      {
        text: '使用指南',
        items: [
          { text: 'Gradio UI 指南', link: '/zh/GRADIO_GUIDE' },
        ],
      },
      {
        text: 'API 参考',
        items: [
          { text: '本地 API', link: '/zh/API' },
          { text: 'OpenRouter API', link: '/zh/Openrouter_API_DOC' },
          { text: '推理', link: '/zh/INFERENCE' },
        ],
      },
      {
        text: '进阶',
        items: [
          { text: 'LoRA 训练', link: '/zh/LoRA_Training_Tutorial' },
          { text: 'GPU 兼容性', link: '/zh/GPU_COMPATIBILITY' },
          { text: '评测', link: '/zh/BENCHMARK' },
        ],
      },
    ],
  }
}

// ---------------------------------------------------------------------------
// Japanese
// ---------------------------------------------------------------------------

function navJA() {
  return [
    {
      text: 'ガイド',
      items: [
        { text: 'インストール', link: '/ja/INSTALL' },
        { text: 'チュートリアル', link: '/ja/Tutorial' },
        { text: 'Gradio UI', link: '/ja/GRADIO_GUIDE' },
      ],
    },
    {
      text: 'API',
      items: [
        { text: 'ローカル API', link: '/ja/API' },
        { text: 'OpenRouter API', link: '/ja/Openrouter_API_DOC' },
      ],
    },
    {
      text: '上級',
      items: [
        { text: 'LoRA 学習', link: '/ja/LoRA_Training_Tutorial' },
        { text: 'GPU 互換性', link: '/ja/GPU_COMPATIBILITY' },
      ],
    },
    {
      text: 'エコシステム',
      link: '/en/awesome',
    },
  ]
}

function sidebarJA() {
  return {
    '/ja/': [
      {
        text: 'はじめに',
        items: [
          { text: 'インストール', link: '/ja/INSTALL' },
          { text: 'チュートリアル (必読)', link: '/ja/Tutorial' },
        ],
      },
      {
        text: '使い方',
        items: [
          { text: 'Gradio UI ガイド', link: '/ja/GRADIO_GUIDE' },
        ],
      },
      {
        text: 'APIリファレンス',
        items: [
          { text: 'ローカル API', link: '/ja/API' },
          { text: 'OpenRouter API', link: '/ja/Openrouter_API_DOC' },
          { text: '推論', link: '/ja/INFERENCE' },
        ],
      },
      {
        text: '上級',
        items: [
          { text: 'LoRA 学習', link: '/ja/LoRA_Training_Tutorial' },
          { text: 'GPU 互換性', link: '/ja/GPU_COMPATIBILITY' },
        ],
      },
    ],
  }
}

// ---------------------------------------------------------------------------
// Korean
// ---------------------------------------------------------------------------

function navKO() {
  return [
    {
      text: '가이드',
      items: [
        { text: '튜토리얼', link: '/ko/Tutorial' },
        { text: 'Gradio UI', link: '/ko/GRADIO_GUIDE' },
      ],
    },
    {
      text: 'API',
      items: [
        { text: '로컬 API', link: '/ko/API' },
        { text: 'OpenRouter API', link: '/ko/Openrouter_API_DOC' },
      ],
    },
    {
      text: '고급',
      items: [
        { text: 'LoRA 학습', link: '/ko/LoRA_Training_Tutorial' },
        { text: 'GPU 호환성', link: '/ko/GPU_COMPATIBILITY' },
      ],
    },
    {
      text: '에코시스템',
      link: '/en/awesome',
    },
  ]
}

function sidebarKO() {
  return {
    '/ko/': [
      {
        text: '시작하기',
        items: [
          { text: '튜토리얼 (필독)', link: '/ko/Tutorial' },
        ],
      },
      {
        text: '사용 가이드',
        items: [
          { text: 'Gradio UI 가이드', link: '/ko/GRADIO_GUIDE' },
        ],
      },
      {
        text: 'API 레퍼런스',
        items: [
          { text: '로컬 API', link: '/ko/API' },
          { text: 'OpenRouter API', link: '/ko/Openrouter_API_DOC' },
          { text: '추론', link: '/ko/INFERENCE' },
        ],
      },
      {
        text: '고급',
        items: [
          { text: 'LoRA 학습', link: '/ko/LoRA_Training_Tutorial' },
          { text: 'GPU 호환성', link: '/ko/GPU_COMPATIBILITY' },
        ],
      },
    ],
  }
}
