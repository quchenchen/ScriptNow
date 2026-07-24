export type CreativeCopyKey =
  | 'novelIdeation'
  | 'novelStoryMap'
  | 'novelWriterReady'
  | 'scriptIdeation'
  | 'scriptStoryMap'
  | 'scriptWriterReady'
  | 'packaging'

const creativeCopy: Record<'zh-CN' | 'en-US', Record<CreativeCopyKey, readonly string[]>> = {
  'zh-CN': {
  novelIdeation: [
    '让叙述声音、人物欲望与长期变化先站稳。',
    '先听见人物心里的潮汐，再决定故事驶向哪里。',
    '一个故事真正开始，是人物终于无法回避自己的渴望。',
    '给尚未成形的命运，多留几条可以生长的路。',
    '先找到那束微光——它会照见人物愿意付出的代价。',
  ],
  novelStoryMap: [
    '让漫长的变化，落在每一次不可撤回的选择里。',
    '把人物的一生拆成章节，却不要拆散命运的回声。',
    '故事不是被排进目录，而是在因果里长出形状。',
    '为每一次转身找到来处，也为每一次抵达留下代价。',
  ],
  novelWriterReady: [
    '这一章已经在门后等待。',
    '人物已经走到纸页边缘，只等你让她开口。',
    '故事来到这一页，接下来要靠文字呼吸。',
    '所有铺垫都在此刻安静下来，等待第一句话。',
  ],
  scriptIdeation: [
    '寻找那个一旦发生，就再也回不到原点的瞬间。',
    '让人物的欲望彼此碰撞，故事才会真正发动。',
    '先点燃三种命运，再选择最值得追随的一束火。',
    '故事的方向，藏在人物最不愿付出的代价里。',
  ],
  scriptStoryMap: [
    '让每一场戏都推开下一扇无法关上的门。',
    '把命运铺进场次，让变化发生在观众眼前。',
    '结构不是刻度，而是人物一步步逼近真相的脚印。',
    '从第一场承诺出发，直到最后一场兑现。',
  ],
  scriptWriterReady: [
    '灯光将亮，这一场正在等待人物入场。',
    '舞台已经安静下来，冲突需要第一句对白。',
    '这一场的空气已经改变，只差人物做出选择。',
    '镜头停在门外，故事正等着被推开。',
  ],
  packaging: [
    '让作品在被打开之前，先发出属于自己的光。',
    '从故事最深的意象里，找到它与读者第一次相遇的样子。',
    '封面不是装饰，是作品递给世界的第一句话。',
    '把人物、气质与命运，凝成读者一眼记住的邀请。',
  ],
  },
  'en-US': {
    novelIdeation: [
      'Let voice, desire, and lasting change find their footing.',
      'Listen for the tide inside the characters before choosing a course.',
      'A story begins when a character can no longer avoid what they want.',
    ],
    novelStoryMap: [
      'Let lasting change live inside choices that cannot be undone.',
      'Give every turn a cause, and every arrival a cost.',
      'A story finds its shape through causality, not a table of contents.',
    ],
    novelWriterReady: [
      'This chapter is waiting behind the door.',
      'The characters have reached the edge of the page. Let them speak.',
      'Every setup has gone quiet, waiting for the first sentence.',
    ],
    scriptIdeation: [
      'Find the moment after which no one can return to the beginning.',
      'Let the characters desires collide until the story ignites.',
      'The direction of a story hides in the price a character refuses to pay.',
    ],
    scriptStoryMap: [
      'Let every scene open a door the next scene cannot close.',
      'Structure is the trail of choices leading a character toward truth.',
      'Begin with a promise in the first scene and fulfil it in the last.',
    ],
    scriptWriterReady: [
      'The lights are coming up. The characters are ready to enter.',
      'The stage is quiet; conflict needs its first line.',
      'The camera waits outside the door. The story is ready to open it.',
    ],
    packaging: [
      'Let the work carry its own light before the first page opens.',
      'A cover is the first sentence a story gives the world.',
      'Turn character, atmosphere, and fate into an invitation readers remember.',
    ],
  },
}

export function pickCreativeCopy(key: CreativeCopyKey, locale: 'zh-CN' | 'en-US' = 'zh-CN'): string {
  const choices = creativeCopy[locale][key]
  return choices[Math.floor(Math.random() * choices.length)]!
}
