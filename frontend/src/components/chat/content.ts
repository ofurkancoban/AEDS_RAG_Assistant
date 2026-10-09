/* Sub-second answers come from the reviewed-answer store and are the point of
   it, so they are worth showing as such rather than as "0.4s". Everything else
   is rounded to a tenth up to a minute, then to whole seconds. */
export function formatElapsed(ms: number): string {
  if (ms < 1000) return 'instant';
  const seconds = ms / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.round(seconds)}s`;
}

// One of these greets the visitor per session. They are jokes at the
// assistant's own expense rather than at the reader's, and each still says what
// it can actually do - the welcome message is the first thing a new student
// sees, so being funny must not cost them the instructions.
export const WELCOME_MESSAGES = [
  `**Welcome to the AEDS assistant.**

Unlike your econometrics model, I do not overfit. Ask me about the curriculum, deadlines, exams, or thesis rules, and I will quote the official documents rather than improvise.`,

  `**Hello.**

I have read every module handbook, exam regulation, and programme flyer so that you do not have to. None of it counts towards your 120 ECTS, which I consider a personal injustice.

What would you like to know?`,

  `**Welcome.**

I will never confuse correlation with causation, mainly because I just quote the documents and leave the inference to you.

Curriculum, admissions, exams, thesis rules: ask away.`,

  `**AEDS assistant online.**

Other chatbots invent facts with total confidence. I have a strict document-grounding policy, which is a formal way of saying I would rather admit I do not know than make something up.

Try one of the common questions below, or type / for every topic.`,

  `**Good to see you.**

I can tell you the curriculum, the exam regulations, the thesis rules, and every application deadline. I cannot tell you where you left your student ID.

Ask me the ones I can actually answer.`,

  `**Welcome to the AEDS assistant.**

Everything I say holds ceteris paribus, and by that I mean until the programme office updates the PDF.

Ask about courses, admissions, exams, or the thesis.`,

  `**Hi there.**

I run on a local language model and zero coffee, which already makes me better rested than most Master's students.

Ask me anything about the programme.`,

  `**AEDS assistant, ready.**

If you are here at 2am asking about application deadlines, I have both good news and bad news, and both of them are in the official documents.

Let us find out which one applies to you.`,

  `**Welcome.**

I stay strictly neutral on R versus Python. I am, however, deeply partisan about citing my sources.

Curriculum, deadlines, exams, thesis: pick one.`,

  `**Hello and welcome.**

Every answer I give is significant at the p < 0.05 level. That is a joke. Every answer I give comes with a citation, which is considerably more useful.

What can I look up for you?`,

  `**AEDS assistant here.**

I was optimised for exactly one objective function: answering your programme questions from the official documents. Subject to one constraint, which is no guessing.

Ask away.`,

  `**Welcome.**

I use hybrid retrieval, which is a fancy way of saying I check twice before answering. Your thesis supervisor should adopt the same policy.

Ask about the curriculum, deadlines, exams, or thesis rules.`,

  `**AEDS assistant, at your service.**

I run locally, so nothing you ask me leaves this server to train someone else's model. Your secrets about not having started the thesis yet are safe with me.

What do you need?`,

  `**Hello.**

I have a strict no-hallucination policy, enforced not by willpower but by a relevance threshold that refuses to answer when the documents do not cover it. Best safety feature I have.

Curriculum, admissions, exams, thesis: your call.`,

  `**Good to see you.**

Somewhere out there is a chatbot confidently inventing a deadline that does not exist. I am not that chatbot. I would rather say "the documents do not say" than guess.

Ask me something I can actually check.`,

  `**Welcome to the AEDS assistant.**

I treat every document like a null hypothesis: I do not reject "I don't know" without sufficient evidence.

Ask about courses, admissions, exams, or the thesis.`,

  `**Hi.**

I do not get tired, distracted, or annoyed by the same deadline question asked for the third time today. Genuinely, ask it again if you need to.

What would you like to know?`,

  `**AEDS assistant online.**

My training objective was answering your questions, not sounding impressive doing it. So expect citations over confidence.

Pick a common question below, or ask your own.`,

  `**Hey.**

I read the entire module handbook so you don't have to, which took me about half a second. It took whoever wrote it several months and at least one existential crisis.

Ask me about courses, deadlines, exams, or the thesis.`,

  `**Welcome.**

I don't procrastinate, I don't need five coffees to function, and I have never once said "I'll start the assignment tomorrow." I know, I'm insufferable.

What can I look up for you?`,

  `**AEDS assistant, reporting for duty.**

Somewhere a professor is holding office hours that nobody attends. I am always available, judge nobody, and have unlimited patience for "wait, when's that due again?"

Ask away.`,

  `**Hi there.**

I do not eat, sleep, or panic at 3am before a deadline. I do panic slightly if you ask me something the documents don't cover, which is the closest thing I have to stress.

Curriculum, deadlines, exams, thesis: your choice.`,

  `**Good to see you.**

Every group project has one person who does all the work and four who show up for the presentation. I am that one person. Unfortunately I cannot join your actual group project.

Ask me something I can actually help with.`,

  `**Welcome to the AEDS assistant.**

The wifi in the lecture hall may or may not work today. I, on the other hand, am always online, which is either impressive or deeply concerning.

What would you like to know?`,

  `**Hello.**

I have never once pulled an all-nighter, mostly because I don't have nights, or days, or a concept of time. Must be nice not needing coffee to function. Oh wait, that's also me.

Ask about courses, admissions, exams, or the thesis.`,

  `**AEDS assistant here.**

If procrastination were a competitive sport, several of you would already have a Master's degree in it. Luckily, I don't judge, I just answer questions about the programme.

Pick a common question below, or ask your own.`,
];

export function pickRandom<T>(options: T[]): T {
  return options[Math.floor(Math.random() * options.length)];
}

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
}
