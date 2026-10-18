"""Phaladipika 26.9-24 (tr. V. Subrahmanya Sastri, 1937): each graha's result in
each house from the Moon sign, quoted as docs/sources/gochara.md transcribes them
from the scan. Classical statements, to be shown as quotations, never as forecasts.
Ketu takes Rahu's lines (MC 4 commentary, p. 142: "ketus tat-phalam eva rasisu vadet").
"""

from __future__ import annotations

PHALADIPIKA_26 = {
    "text": "Phaladīpikā",
    "verse": "26.1–24",
    "edition": "Mantreśvara, translated by V. Subrahmanya Sastri, First edition, 1937",
    "page": "286–296",
}

# graha: (verse, page or None, the lines for houses 1-12)
RESULTS: dict[str, tuple[str, str | None, tuple[str, ...]]] = {
    "Sun": (
        "26.9–11",
        None,
        (
            "fatigue and loss of wealth. He will become irritated and suffer from diseases. "
            "He will undertake a wearisome journey",
            "loss of wealth; and the person will be unhappy. He will be duped by others, and "
            "will be obstinate",
            "acquisition of a new position, advent of moneys, happiness, freedom from sickness "
            "and destruction of enemies",
            "diseases; and there will often arise impediments to the native in the matter of "
            "his sexual enjoyments",
            "Mental agitation, ill-health and embarrassment in all possible ways",
            "remove all diseases, destroy enemies, and dispel all sorrows and mental anxieties",
            "wearisome travelling, diseases of the stomach and the anus … humiliation",
            "fear, and diseases. He will be drawn to a quarrel. He will incur royal displeasure "
            "and he will suffer also from excessive heat",
            "danger, humiliation, separation from his kith and kin and mental depression",
            "a very mighty undertaking will be successfully completed",
            "A new position, honour, wealth and freedom from diseases",
            "sorrow, loss of wealth, quarrel with one's friends and fever",
        ),
    ),
    "Moon": (
        "26.12",
        "290",
        (
            "dawning of fortune",
            "loss of wealth",
            "success",
            "fear",
            "sorrow",
            "freedom from disease",
            "happiness",
            "untoward events",
            "sickness",
            "attainment of one's cherished wishes",
            "joy",
            "expenditure",
        ),
    ),
    "Mars": (
        "26.13–16",
        None,
        (
            "dejection of the mind, separation from one's relations and diseases caused by "
            "(impurity of) blood, bile or heat",
            "fear, hot words, and loss of wealth",
            "success (in everything) and happiness through the attainment of golden ornaments",
            "loss of position, disease of the belly … and sorrow through relations",
            "fever, improper desires, mental anguish caused through one's son, or quarrel with "
            "one's relations",
            "termination of strife and the withdrawal of enemies, alleviation of disease, "
            "victory, financial gain and success in all undertakings",
            "misunderstanding with one's own wife, eye-disease, stomach-ache and the like",
            "fever; his body will become soiled by blood. He will have lost his wealth and honour",
            "humiliation through loss of wealth, etc. The native's gait will become retarded "
            "due to bodily weakness",
            "will either misbehave … or he will fail in his attempts. He will have exhaustion",
            "financial gain, freedom from sickness, addition to landed property, etc.",
            "loss of wealth, and the native will suffer from diseases caused by excessive heat",
        ),
    ),
    "Mercury": (
        "26.17",
        "292",
        (
            "loss of wealth",
            "financial gain",
            "fear from enemies",
            "influx of money",
            "quarrel with one's wife and children",
            "success",
            "misunderstandings",
            "acquisition of children, wealth, etc.",
            "impediments",
            "happiness all round",
            "prosperity",
            "fear of humiliation",
        ),
    ),
    "Jupiter": (
        "26.18–20",
        None,
        (
            "may have to leave his country, incur heavy expenditure and bear ill-will towards "
            "others",
            "will acquire money and will have domestic happiness. His words will have weight",
            "loss of position, separation from one's friends, obstacle to business and disease",
            "sorrow through relations; the person will suffer humiliation and will have to "
            "apprehend danger from cattle",
            "Acquisition of children, friendship with the good and royal favour",
            "trouble from his enemies and cousins. He will also suffer from diseases",
            "will travel on an auspicious undertaking, will be happy with his wife and will be "
            "blessed with children",
            "fatigue by wearisome journeys, will be unlucky, suffer loss of money and will be "
            "miserable",
            "will succeed in enjoying all prosperity",
            "danger to one's property, position and children",
            "Acquisition of children, new position, honour and the like",
            "grief and fear caused through property",
        ),
    ),
    "Venus": (
        "26.21",
        "294",
        (
            "all kinds of enjoyments",
            "financial gain",
            "prosperity",
            "increase of happiness and friends",
            "acquisition of children",
            "mishap",
            "trouble to wife",
            "wealth",
            "happiness",
            "quarrel",
            "safety",
            "acquisition of money",
        ),
    ),
    "Saturn": (
        "26.22–23",
        "294–295",
        (
            "will suffer from disease; he will perform funeral rites",
            "trouble to wealth and children",
            "acquisition of position or employment, servants and money",
            "loss of wife, relation and wealth",
            "wealth will decline, there will be loss of children and the native's mind will "
            "become confused",
            "happiness all round",
            "the native's wife will suffer; there will be travelling; he will be depressed by fear",
            "loss in children, cattle, friends and wealth. The native will also suffer from "
            "disease",
            "loss in finance. There will be many obstacles for the native's doing any good "
            "action. A relative who is equal to the father will die. There will be perpetual "
            "sorrow",
            "will make the native do a sinful deed. There will be loss of honour. The person may "
            "suffer from disease",
            "confers all kinds of happiness and wealth on the native, who will also receive "
            "unique honour",
            "wearied by being engaged in a worthless and fruitless business. He will be robbed "
            "of his moneys by his enemies. His wife and sons will suffer from sickness",
        ),
    ),
    "Rahu": (
        "26.24",
        "296",
        (
            "sickness or death",
            "loss of wealth",
            "happiness",
            "sorrow",
            "financial loss",
            "happiness",
            "loss",
            "danger to life",
            "loss",
            "gain",
            "happiness",
            "expenditure",
        ),
    ),
}
RESULTS["Ketu"] = (
    "26.24 (Rahu's; Ketu the same per MC 4 commentary, p. 142)",
    "296",
    RESULTS["Rahu"][2],
)
