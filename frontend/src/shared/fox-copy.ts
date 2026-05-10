export const foxCopy = {
  onboarding: {
    greeting: "你来了。期末了还是还没死心想好好学？",
    modePick: "选一个吧，我对时间紧的人和不紧的人态度可不一样。",
    examChoice: "我要备考",
    studyChoice: "日常学习",
    createCourse: "先建一门课，别空着手。",
    uploadPrompt: "把材料扔进来，PDF、PPT、笔记都行。",
    noFile: "没有文件？先告诉我老师讲了什么。",
    done: "好了，可以去学习了。",
  },
  bookshelf: {
    empty: "你来了。还没有课程？先建一个再说。",
    emptyHint: "点上面那个橙色的按钮，别等了。",
    importBtn: "导入课程表",
    createBtn: "创建课程",
  },
  skeleton: {
    generating: "好，我去消化一下，你先等等。",
    done: "我大概看完了。这门课你最薄的地方好像是{chapter}，要先从这里开始吗？",
    empty: "材料还在消化中，骨架图即将生成",
    processing: "狐狸正在啃材料，每 10 秒自动检查...",
  },
  chat: {
    empty: "有什么关于课程的问题？尽管问，别问超范围的，我不会答。",
    emptyHint: "狐狸只基于课程材料回答",
    refusal: "这个问题超出了{title}的范围，我不知道。别想骗我乱说。",
    placeholder: "问点关于课程的问题...",
    error: "哎呀，出了点问题……不是我干的。再试一次吧。",
  },
  review: {
    prompt: "期末了？让狐狸带你过一遍。",
    noPlanPrompt: "让小狐狸帮你备考",
    generating: "小狐狸正在为你制定复习计划...",
    stepStart: "今天来搞定{chapter}的这几个概念，大约{minutes}分钟。",
    stepDone: "不错，明天继续{chapter}。",
    countdown: "距离考试还有 {days} 天",
    countdownUrgent: "距离考试不到 {days} 天",
    switchSuggestion: "建议切换到备考模式",
    startBtn: "开始复习",
    doneBtn: "完成了",
    pauseBtn: "今天先到这",
    allDone: "全部完成了，去考试吧。",
  },
  material: {
    empty: "还没有上传材料",
    uploadPrompt: "把材料扔进来，PDF、PPT、笔记都行。没有文件？先告诉我老师讲了什么。",
    dragHint: "拖拽文件到此处",
    uploading: "上传中...",
    success: "上传成功!",
    degraded: "降级解析",
    retry: "重试",
  },
  errors: {
    generic: "哎呀，出了点问题……再试一次吧。",
    loadFailed: "加载失败了，点重试试试。",
    retry: "重试",
  },
};

export function foxSay(text: string, ...args: (string | number)[]): string {
  let result = text;
  for (let i = 0; i < args.length; i++) {
    result = result.replace(`{${i}}`, String(args[i]));
  }
  // Also support named placeholders
  for (const arg of args) {
    if (typeof arg === "string") {
      for (const key of ["chapter", "title", "days", "minutes", "hours"]) {
        result = result.replace(`{${key}}`, String(arg));
        break; // Replace one at a time with positional args
      }
    }
  }
  return result;
}
