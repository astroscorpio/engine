"""Phaladipika 26.9-24 (tr. V. Subrahmanya Sastri, 1937): each graha's result in
each house from the Moon sign, quoted as docs/sources/gochara.md transcribes them
from the scan. Classical statements, to be shown as quotations, never as forecasts.
Ketu takes Rahu's lines (MC 4.1-3 commentary, p. 142: "ketus tat-phalam eva rasisu vadet").
"""

from __future__ import annotations

PHALADIPIKA_26 = {
    "text": "Phaladīpikā",
    "verse": "26.1–24",
    "edition": "Mantreśvara, translated by V. Subrahmanya Sastri, First edition, 1937",
    "page": "286–296",
}

# graha: (verse, page, the lines for houses 1-12)
RESULTS: dict[str, tuple[str, str | None, tuple[str, ...]]] = {
    "Sun": (
        "26.9–11",
        "289–290",
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
        "290–292",
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
        "293–294",
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
    "26.24 (Rahu's; Ketu the same per MC 4.1–3 commentary, p. 142)",
    "296",
    RESULTS["Rahu"][2],
)

# PD 26.9-24 as printed in the 1937 printing (gochara.md §5a: research's reading of the scan,
# 19 Oct 2026), one string per printed line. Served as meta.gocharaVerses beside each graha's
# lines; Ketu reads Rahu's.
VERSES: dict[str, tuple[str, ...]] = {
    "Sun": (
        "जन्मन्यायासदाता क्षपयति विभवान् क्रोधरोगाध्वदाता",
        "वित्तभ्रंशं द्वितीये दिशति न सुखदो वञ्चनामाग्रहं च ।",
        "स्थानप्राप्तिं तृतीये धननिचयमुदाकल्यकृच्चारिहन्ता",
        "रोगान् दत्ते चतुर्थे जनयति च मुहुः स्रग्धराभोगविघ्नम् ॥९॥",
        "चित्तक्षोभं सुतस्थो वितरति बहुशो रोगमोहादिदाता",
        "षष्ठेऽर्को हन्ति रोगान् क्षपयति च रिपूञ्छोकमोहान्प्रमार्ष्टि ।",
        "अध्वानं सप्तमस्थो जठरगुदभयं दैन्यभावं च तस्मै",
        "रुक्त्रासावष्टमस्थः कलयति कलहं राजभीतिं च तापम् ॥१०॥",
        "आपद्दैन्यं तपसि विरहं चित्तचेष्टानिरोधं",
        "प्राप्नोत्युग्रां दशमगृहगे कर्मसिद्धिं दिनेशे ।",
        "स्थानं मानं विभवमपि चैकादशे रोगनाशं",
        "क्लेशं वित्तक्षयमपि सुहृद्वैरमन्त्ये ज्वरं च ॥११॥",
    ),
    "Moon": (
        "क्रमेण भाग्योदयमर्थहानिं जयं भयं शोकमरोगतां च ।",
        "सुखान्यनिष्टं गदमिष्टसिद्धिं मोदं व्ययं च प्रददाति चन्द्रः ॥१२॥",
    ),
    "Mars": (
        "अन्तः शोकं स्वजनविरहं रक्तपित्तोष्णरोगं",
        "लग्ने वित्ते भयमपि गिरां दोषमर्थक्षयं च ।",
        "धैर्ये भौमो जनयति जयं स्वर्णभूषाप्रमोदं",
        "स्थानभ्रंशं रुजमुदरजां बन्धुदुःखं चतुर्थे ॥१३॥",
        "ज्वरमनुचितचिन्तां पुत्रहेतुव्यथां वा",
        "कलयति कलहं स्वैः पञ्चमे भूमिपुत्रः ।",
        "रिपुकलहनिवृत्तिं रोगशान्तिं च षष्ठे",
        "विजयमथ धनाप्तिं सर्वकार्यानुकूल्यम् ॥१४॥",
        "कलत्रकलहाक्षिरुग्जठररोगकृत्सप्तमे",
        "ज्वरक्षतजकर्शितो विगतवित्तमानोऽष्टमे ।",
        "कुजे नवमसंस्थिते परिभवोऽर्थनाशादिभि-",
        "र्विलम्बितगतिर्भवत्यबलदेहधातुक्षयैः ॥१५॥",
        "दुश्चेष्टा वा कर्मविघ्नः श्रमः खे द्रव्यारोग्यक्षेत्रवृद्धिश्च लाभे ।",
        "भौमः खेटो गोचरे द्वादशस्थो द्रव्यच्छेदस्ताप उष्णामयाद्यैः ॥१६॥",
    ),
    "Mercury": (
        "वित्तक्षयं श्रियमरातिभयं धनाप्तिं",
        "भार्यातनूजकलहं विजयं विरोधम् ।",
        "पुत्रार्थलाभमथ विघ्नमशेषसौख्यं",
        "पुष्टिं पराभवभयं प्रकरोति चान्द्रिः ॥१७॥",
    ),
    "Jupiter": (
        "जीवे जन्मनि देशनिर्गमनमप्यर्थच्युतिं शत्रुतां",
        "प्राप्नोति द्रविणं कुटुम्बसुखमप्यर्थे स्ववाचां फलम् ।",
        "दुश्चिक्ये स्थितिनाशमिष्टवियुतिं कार्यान्तरायं रुजं",
        "दुःखैर्बन्धुजनोद्भवैश्च हिबुके दैन्यं चतुष्पाद्भयम् ॥१८॥",
        "पुत्रोत्पत्तिमुपैति सज्जनयुतिं राजानुकूल्यं सुते",
        "षष्ठे मन्त्रिणि पीडयन्ति रिपवः स्वज्ञातयो व्याधयः ।",
        "यात्रां शोभनहेतवे वनितया सौख्यं सुताप्तिं स्मरे",
        "मार्गक्लेशमनिष्टमष्टमगते नष्टं धनैः कष्टताम् ॥१९॥",
        "भाग्ये जीवे सर्वसौभाग्यसिद्धिः",
        "कर्मण्यर्थस्थानपुत्रादिपीडा ।",
        "लाभे पुत्रस्थानमानादिलाभो",
        "रिःफे दुःखं साध्वसं द्रव्यहेतोः ॥२०॥",
    ),
    "Venus": (
        "अखिलविषयभोगं वित्तसिद्धिं विभूतिं",
        "सुखसुहृदभिवृद्धिं पुत्रलब्धिं विपत्तिम् ।",
        "दिशति युवतिपीडां सम्पदं वा सुखाप्तिं",
        "कलहमभयमर्थप्राप्तिमिन्द्रारिमन्त्री ॥२१॥",
    ),
    "Saturn": (
        "रोगाशौचक्रियाप्तिं धनसुतविहतिं स्थानभृत्यार्थलाभं",
        "स्त्रीबन्ध्वर्थप्रणाशं द्रविणसुतमतिप्रच्युतिं सर्वसौख्यम् ।",
        "स्त्रीरोगाध्वावभीतिं स्वसुतपशुसुहृद्वित्तनाशामयार्तिं",
        "जन्मादेरष्टमान्तं दिशति पदवशेनार्कसूनुः क्रमेण ॥२२॥",
        "दारिद्र्यं धर्मविघ्नं पितृसमविलयं नित्यदुःखं शुभस्थो",
        "दुर्व्यापारप्रवृत्तिं कलयति दशमे मानभङ्गं रुजं वा ।",
        "सौख्यान्येकादशस्थो बहुविधविभवप्राप्तिमुत्कृष्टकीर्तिं",
        "विश्रान्तिं व्यर्थकार्याद्यपहृतिमरिभिः स्त्रीसुतव्याधिमन्त्ये ॥२३॥",
    ),
    "Rahu": (
        "देहक्षयं वित्तविनाशसौख्ये दुःखार्थनाशौ सुखनाशमृत्यून् ।",
        "हानिं च लाभं सुभगं व्ययं च कुर्यात्तमो जन्मगृहात्क्रमेण ॥२४॥",
    ),
}
