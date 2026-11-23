# -*- coding: utf-8 -*-
"""前三章台词表：手工标注说话人 + 情绪。

who: E=Edmund(Hooper) / C=Charles / M=Mrs Kingshaw
emo: None 表示不打标签（模型默认平读）
"""

# (idx, who, emo, text)
PLAN = [
    # ---- ch1: Edmund vs 父亲 ----
    (2,  "E", "calm",       "I am never afraid."),
    (5,  "E", "disgusted",  "All he looks like, is one of his dead old moths."),
    (8,  "E", "calm",       "That won't be anything new, will it?"),
    (11, "E", "calm",       "I wouldn't do any harm. Why can't I go?"),
    (14, "E", "calm",       "Can I have the key now, then?"),
    (17, "E", "melancholic", "There's nobody to play cricket with."),
    (19, "E", "calm",       "Anyway, I don't like cricket."),
    (30, "E", "calm",       "The butterflies were just a craze last term. We caught larvae and watched them hatch. Nobody's interested now."),
    (31, "E", "calm",       "Why didn't you bring me here before?"),
    (33, "E", "calm",       "That's years ago."),
    (35, "E", "calm",       "I suppose you quarrelled with grandfather then."),
    (46, "E", "happy",      "It is my house, it is private. I got here first. Nobody should come here."),
    # ---- ch2: Charles 到来 ----
    (44, "C", "calm",       "I'm quite all right. There isn't anything wrong at all."),
    (45, "C", "calm",       "There's nothing wrong."),
    (50, "C", "surprised",  "Oh, what is it? What have you found?"),
    (51, "E", "calm",       "Nothing, it's nothing. It's only a pebble."),
    (52, "E", "happy",      "I didn't want you to come here."),
    (53, "E", "happy",      "Why have you come here?"),
    (54, "E", "happy",      "Why did you have to find somewhere new to live?"),
    (55, "E", "calm",       "When my father dies, this house will belong to me. I shall be master. It'll all be mine."),
    (56, "C", "calm",       "That's nothing. It's only an old house."),
    (57, "E", "calm",       "Downstairs is something very valuable. Something you've never seen."),
    (58, "C", "calm",       "What then?"),
    (59, "E", "calm",       "My grandfather died in this room. Not very long ago, either. He lay and died in that bed. Now it's your bed."),
    # ---- ch3: 两个男孩互相试探 ----
    (60, "E", "calm",       "Where did you live before?"),
    (61, "C", "calm",       "In a flat."),
    (62, "E", "calm",       "Your own flat?"),
    (63, "C", "calm",       "Yes. No. Well, it was in somebody's house."),
    (64, "E", "calm",       "You were only tenants, then."),
    (65, "E", "calm",       "It wasn't really yours."),
    (66, "E", "calm",       "Why didn't your father buy a proper house?"),
    (67, "C", "sad",        "My father's dead."),
    (68, "C", "sad",        "Well, my mother can't afford to buy us a house, can she? We can't help that."),
    (69, "E", "calm",       "Your father should have left you some money, then, shouldn't he? Didn't he have a house?"),
    (70, "C", "sad",        "Yes, he did. But it had to be sold."),
    (71, "C", "sad",        "I don't know."),
    (72, "C", "sad",        "To pay off all his debts."),
    (74, "E", "calm",       "Do you remember your father?"),
    (75, "C", "sad",        "Oh, yes. Well, a bit. He was a pilot, once. He was in the Battle of Britain. I've got..."),
    (76, "C", "sad",        "...I've got a picture of him."),
    (77, "E", "calm",       "Is it a picture of him in the Battle?"),
    (78, "C", "sad",        "No. But..."),
    (79, "E", "happy",      "I don't believe you. You're a liar. The Battle of Britain was in the war."),
    (80, "C", "calm",       "Well, I know that. Everybody knows that."),
    (81, "E", "happy",      "It was years ago. Dozens of years. It was history. He couldn't have been in it."),
    (83, "C", "sad",        "Here's the picture. Look, that's my father."),
    (84, "E", "happy",      "When did he die, I said."),
    (85, "C", "sad",        "A few years ago. I was about five. Or six."),
    (86, "E", "calm",       "He would have been pretty old by then. How old was he?"),
    (87, "C", "sad",        "I don't know. Quite old, I suppose. Look, then, there's the photograph."),
    (88, "C", "sad",        "He's old, I told you. When he was in the Battle of Britain, he was twenty. That was the war."),
    (89, "E", "calm",       "Where do you go to school?"),
    (90, "C", "calm",       "In Wales."),
    (91, "E", "calm",       "I should think there would be about a hundred schools in Wales. More than a hundred."),
    (92, "C", "calm",       "It's called St Vincent's."),
    (93, "E", "calm",       "Is it a proper school?"),
]

# 无引号的心理描写 / 内心独白（用角色本音，轻声内敛）
INNER = [
    ("I", "E", None, "His skin is already dead, he thought. It is old and dry."),
    ("I", "E", None, "The sick room smelled sour."),
    ("I", "C", None, "He would not let them see that he was afraid."),
    ("I", "C", None, "It was not his house. Nothing here was his."),
]

REFS = {
    "C": ("G:/_setup/castle_fr_ref/CH_neutral.wav",
          "Je suis né comme ça aussi? Vous êtes M. Bréaud? Moi, je suis Charles Vernet. Non. Ça va mieux, maintenant. "
          "Non, monsieur. Et si elle, elle vous aime pas? Laisse. C'est moi qui t'invite. je suis encore très riche. "
          "Mais il pouvait rien m'arriver. Maman, j'aurai plus jamais peur. Maman, je suis d'Artagnan. Non, maman. "
          "C'est le cadeau de Thomas. Tu peux plus rien me faire, maintenant."),
    "E": ("G:/_setup/castle_fr_ref/6_hooper_calm.wav",
          "N'accablez point, madame, un prince malheureux. Il ne faut point ici nous attendrir tous deux. "
          "Un trouble assez cruel m'agite et me dévore sans que des pleurs si chers me déchirent encore. "
          "J'ai dit à papa que je voulais rester seul avec vous."),
}
