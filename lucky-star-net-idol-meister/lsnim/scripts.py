"""Scripts of sc.cpk: glyph text, messages, menus, quiz database, voiced lines."""
import os
import struct

from .tables import BLOCK_ORDER, QUIZ_CATEGORY_SIZE, QUIZ_VOICES_FIRST, QUIZ_VOICE_CATEGORY
from .cpk import decompress_crilayla, list_entries


#
# Text is stored as little-endian 16-bit glyph indices into the game font (lt.bin),
# not as Shift-JIS. Message layout:
#     FF65 <msg_id> <flag> FFF0 <msg_id> [speaker glyphs FFFF] text ... (FFFE = line break) FFFB
#     FF37 FFFF 0000 FFF0 <msg_id> FFFF text ... FFFB                    (event text)
# Choice menus:
#     FFFD FFF7 <arg> FFFC FFFF (choice glyphs FFFF 0000 <target>)* FFFF
#
# The quiz database (file 00595 of sc.cpk) is also supported: an offset table
# followed by entries  FFFC FFF0 <id> [label] FFFF question FFFB FFF0 <id+1> FFFF answers FFFB FFFF

# Glyph index -> character (3650 glyphs). Indices 0-3455 follow Shift-JIS (cp932) order
# without box-drawing / NEC row 13; 3456+ are extra kanji appended by the developers.
GLYPHS = (
    '\u3000、。，．・：；？！゛゜´｀¨＾￣＿ヽヾゝゞ〃仝々〆〇ー―‐／＼～∥｜…‥‘’“”（）〔〕［］｛｝〈〉《》「」『』【】＋－±×÷'
    '＝≠＜＞≦≧∞∴♂♀°′″℃￥＄￠￡％＃＆＊＠§☆★○●◎◇◆□■△▲▽▼※〒→←↑↓〓∈∋⊆⊇⊂⊃∪∩∧∨￢⇒⇔∀∃∠⊥⌒∂∇'
    '≡≒≪≫√∽∝∵∫∬Å‰♯♭♪†‡¶０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊ'
    'ｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねのはば'
    'ぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑをんァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソ'
    'ゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヰヱヲンヴヵヶΑΒΓΔΕΖΗ'
    'ΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψωАБВГДЕЁЖЗИЙКЛМНОПРСТУФХ'
    'ЦЧШЩЪЫЬЭЮЯабвгдеёжзийклмнопрстуфхцчшщъыьэюя亜唖娃阿哀愛挨姶逢葵茜穐悪握渥旭葦芦鯵梓圧'
    '斡扱宛姐虻飴絢綾鮎或粟袷安庵按暗案闇鞍杏以伊位依偉囲夷委威尉惟意慰易椅為畏異移維緯胃萎衣謂違遺医井亥域育郁磯一壱溢逸稲茨芋鰯允印'
    '咽員因姻引飲淫胤蔭院陰隠韻吋右宇烏羽迂雨卯鵜窺丑碓臼渦嘘唄欝蔚鰻姥厩浦瓜閏噂云運雲荏餌叡営嬰影映曳栄永泳洩瑛盈穎頴英衛詠鋭液疫益'
    '駅悦謁越閲榎厭円園堰奄宴延怨掩援沿演炎焔煙燕猿縁艶苑薗遠鉛鴛塩於汚甥凹央奥往応押旺横欧殴王翁襖鴬鴎黄岡沖荻億屋憶臆桶牡乙俺卸恩温'
    '穏音下化仮何伽価佳加可嘉夏嫁家寡科暇果架歌河火珂禍禾稼箇花苛茄荷華菓蝦課嘩貨迦過霞蚊俄峨我牙画臥芽蛾賀雅餓駕介会解回塊壊廻快怪悔'
    '恢懐戒拐改魁晦械海灰界皆絵芥蟹開階貝凱劾外咳害崖慨概涯碍蓋街該鎧骸浬馨蛙垣柿蛎鈎劃嚇各廓拡撹格核殻獲確穫覚角赫較郭閣隔革学岳楽額'
    '顎掛笠樫橿梶鰍潟割喝恰括活渇滑葛褐轄且鰹叶椛樺鞄株兜竃蒲釜鎌噛鴨栢茅萱粥刈苅瓦乾侃冠寒刊勘勧巻喚堪姦完官寛干幹患感慣憾換敢柑桓棺'
    '款歓汗漢澗潅環甘監看竿管簡緩缶翰肝艦莞観諌貫還鑑間閑関陥韓館舘丸含岸巌玩癌眼岩翫贋雁頑顔願企伎危喜器基奇嬉寄岐希幾忌揮机旗既期棋'
    '棄機帰毅気汽畿祈季稀紀徽規記貴起軌輝飢騎鬼亀偽儀妓宜戯技擬欺犠疑祇義蟻誼議掬菊鞠吉吃喫桔橘詰砧杵黍却客脚虐逆丘久仇休及吸宮弓急救'
    '朽求汲泣灸球究窮笈級糾給旧牛去居巨拒拠挙渠虚許距鋸漁禦魚亨享京供侠僑兇競共凶協匡卿叫喬境峡強彊怯恐恭挟教橋況狂狭矯胸脅興蕎郷鏡響'
    '饗驚仰凝尭暁業局曲極玉桐粁僅勤均巾錦斤欣欽琴禁禽筋緊芹菌衿襟謹近金吟銀九倶句区狗玖矩苦躯駆駈駒具愚虞喰空偶寓遇隅串櫛釧屑屈掘窟沓'
    '靴轡窪熊隈粂栗繰桑鍬勲君薫訓群軍郡卦袈祁係傾刑兄啓圭珪型契形径恵慶慧憩掲携敬景桂渓畦稽系経継繋罫茎荊蛍計詣警軽頚鶏芸迎鯨劇戟撃激'
    '隙桁傑欠決潔穴結血訣月件倹倦健兼券剣喧圏堅嫌建憲懸拳捲検権牽犬献研硯絹県肩見謙賢軒遣鍵険顕験鹸元原厳幻弦減源玄現絃舷言諺限乎個古'
    '呼固姑孤己庫弧戸故枯湖狐糊袴股胡菰虎誇跨鈷雇顧鼓五互伍午呉吾娯後御悟梧檎瑚碁語誤護醐乞鯉交佼侯候倖光公功効勾厚口向后喉坑垢好孔孝'
    '宏工巧巷幸広庚康弘恒慌抗拘控攻昂晃更杭校梗構江洪浩港溝甲皇硬稿糠紅紘絞綱耕考肯肱腔膏航荒行衡講貢購郊酵鉱砿鋼閤降項香高鴻剛劫号合'
    '壕拷濠豪轟麹克刻告国穀酷鵠黒獄漉腰甑忽惚骨狛込此頃今困坤墾婚恨懇昏昆根梱混痕紺艮魂些佐叉唆嵯左差査沙瑳砂詐鎖裟坐座挫債催再最哉塞'
    '妻宰彩才採栽歳済災采犀砕砦祭斎細菜裁載際剤在材罪財冴坂阪堺榊肴咲崎埼碕鷺作削咋搾昨朔柵窄策索錯桜鮭笹匙冊刷察拶撮擦札殺薩雑皐鯖捌'
    '錆鮫皿晒三傘参山惨撒散桟燦珊産算纂蚕讃賛酸餐斬暫残仕仔伺使刺司史嗣四士始姉姿子屍市師志思指支孜斯施旨枝止死氏獅祉私糸紙紫肢脂至視'
    '詞詩試誌諮資賜雌飼歯事似侍児字寺慈持時次滋治爾璽痔磁示而耳自蒔辞汐鹿式識鴫竺軸宍雫七叱執失嫉室悉湿漆疾質実蔀篠偲柴芝屡蕊縞舎写射'
    '捨赦斜煮社紗者謝車遮蛇邪借勺尺杓灼爵酌釈錫若寂弱惹主取守手朱殊狩珠種腫趣酒首儒受呪寿授樹綬需囚収周宗就州修愁拾洲秀秋終繍習臭舟蒐'
    '衆襲讐蹴輯週酋酬集醜什住充十従戎柔汁渋獣縦重銃叔夙宿淑祝縮粛塾熟出術述俊峻春瞬竣舜駿准循旬楯殉淳準潤盾純巡遵醇順処初所暑曙渚庶緒'
    '署書薯藷諸助叙女序徐恕鋤除傷償勝匠升召哨商唱嘗奨妾娼宵将小少尚庄床廠彰承抄招掌捷昇昌昭晶松梢樟樵沼消渉湘焼焦照症省硝礁祥称章笑粧'
    '紹肖菖蒋蕉衝裳訟証詔詳象賞醤鉦鍾鐘障鞘上丈丞乗冗剰城場壌嬢常情擾条杖浄状畳穣蒸譲醸錠嘱埴飾拭植殖燭織職色触食蝕辱尻伸信侵唇娠寝審'
    '心慎振新晋森榛浸深申疹真神秦紳臣芯薪親診身辛進針震人仁刃塵壬尋甚尽腎訊迅陣靭笥諏須酢図厨逗吹垂帥推水炊睡粋翠衰遂酔錐錘随瑞髄崇嵩'
    '数枢趨雛据杉椙菅頗雀裾澄摺寸世瀬畝是凄制勢姓征性成政整星晴棲栖正清牲生盛精聖声製西誠誓請逝醒青静斉税脆隻席惜戚斥昔析石積籍績脊責'
    '赤跡蹟碩切拙接摂折設窃節説雪絶舌蝉仙先千占宣専尖川戦扇撰栓栴泉浅洗染潜煎煽旋穿箭線繊羨腺舛船薦詮賎践選遷銭銑閃鮮前善漸然全禅繕膳'
    '糎噌塑岨措曾曽楚狙疏疎礎祖租粗素組蘇訴阻遡鼠僧創双叢倉喪壮奏爽宋層匝惣想捜掃挿掻操早曹巣槍槽漕燥争痩相窓糟総綜聡草荘葬蒼藻装走送'
    '遭鎗霜騒像増憎臓蔵贈造促側則即息捉束測足速俗属賊族続卒袖其揃存孫尊損村遜他多太汰詑唾堕妥惰打柁舵楕陀駄騨体堆対耐岱帯待怠態戴替泰'
    '滞胎腿苔袋貸退逮隊黛鯛代台大第醍題鷹滝瀧卓啄宅托択拓沢濯琢託鐸濁諾茸凧蛸只叩但達辰奪脱巽竪辿棚谷狸鱈樽誰丹単嘆坦担探旦歎淡湛炭短'
    '端箪綻耽胆蛋誕鍛団壇弾断暖檀段男談値知地弛恥智池痴稚置致蜘遅馳築畜竹筑蓄逐秩窒茶嫡着中仲宙忠抽昼柱注虫衷註酎鋳駐樗瀦猪苧著貯丁兆'
    '凋喋寵帖帳庁弔張彫徴懲挑暢朝潮牒町眺聴脹腸蝶調諜超跳銚長頂鳥勅捗直朕沈珍賃鎮陳津墜椎槌追鎚痛通塚栂掴槻佃漬柘辻蔦綴鍔椿潰坪壷嬬紬'
    '爪吊釣鶴亭低停偵剃貞呈堤定帝底庭廷弟悌抵挺提梯汀碇禎程締艇訂諦蹄逓邸鄭釘鼎泥摘擢敵滴的笛適鏑溺哲徹撤轍迭鉄典填天展店添纏甜貼転顛'
    '点伝殿澱田電兎吐堵塗妬屠徒斗杜渡登菟賭途都鍍砥砺努度土奴怒倒党冬凍刀唐塔塘套宕島嶋悼投搭東桃梼棟盗淘湯涛灯燈当痘祷等答筒糖統到董'
    '蕩藤討謄豆踏逃透鐙陶頭騰闘働動同堂導憧撞洞瞳童胴萄道銅峠鴇匿得徳涜特督禿篤毒独読栃橡凸突椴届鳶苫寅酉瀞噸屯惇敦沌豚遁頓呑曇鈍奈那'
    '内乍凪薙謎灘捺鍋楢馴縄畷南楠軟難汝二尼弐迩匂賑肉虹廿日乳入如尿韮任妊忍認濡禰祢寧葱猫熱年念捻撚燃粘乃廼之埜嚢悩濃納能脳膿農覗蚤巴'
    '把播覇杷波派琶破婆罵芭馬俳廃拝排敗杯盃牌背肺輩配倍培媒梅楳煤狽買売賠陪這蝿秤矧萩伯剥博拍柏泊白箔粕舶薄迫曝漠爆縛莫駁麦函箱硲箸肇'
    '筈櫨幡肌畑畠八鉢溌発醗髪伐罰抜筏閥鳩噺塙蛤隼伴判半反叛帆搬斑板氾汎版犯班畔繁般藩販範釆煩頒飯挽晩番盤磐蕃蛮匪卑否妃庇彼悲扉批披斐'
    '比泌疲皮碑秘緋罷肥被誹費避非飛樋簸備尾微枇毘琵眉美鼻柊稗匹疋髭彦膝菱肘弼必畢筆逼桧姫媛紐百謬俵彪標氷漂瓢票表評豹廟描病秒苗錨鋲蒜'
    '蛭鰭品彬斌浜瀕貧賓頻敏瓶不付埠夫婦富冨布府怖扶敷斧普浮父符腐膚芙譜負賦赴阜附侮撫武舞葡蕪部封楓風葺蕗伏副復幅服福腹複覆淵弗払沸仏'
    '物鮒分吻噴墳憤扮焚奮粉糞紛雰文聞丙併兵塀幣平弊柄並蔽閉陛米頁僻壁癖碧別瞥蔑箆偏変片篇編辺返遍便勉娩弁鞭保舗鋪圃捕歩甫補輔穂募墓慕'
    '戊暮母簿菩倣俸包呆報奉宝峰峯崩庖抱捧放方朋法泡烹砲縫胞芳萌蓬蜂褒訪豊邦鋒飽鳳鵬乏亡傍剖坊妨帽忘忙房暴望某棒冒紡肪膨謀貌貿鉾防吠頬'
    '北僕卜墨撲朴牧睦穆釦勃没殆堀幌奔本翻凡盆摩磨魔麻埋妹昧枚毎哩槙幕膜枕鮪柾鱒桝亦俣又抹末沫迄侭繭麿万慢満漫蔓味未魅巳箕岬密蜜湊蓑稔'
    '脈妙粍民眠務夢無牟矛霧鵡椋婿娘冥名命明盟迷銘鳴姪牝滅免棉綿緬面麺摸模茂妄孟毛猛盲網耗蒙儲木黙目杢勿餅尤戻籾貰問悶紋門匁也冶夜爺耶'
    '野弥矢厄役約薬訳躍靖柳薮鑓愉愈油癒諭輸唯佑優勇友宥幽悠憂揖有柚湧涌猶猷由祐裕誘遊邑郵雄融夕予余与誉輿預傭幼妖容庸揚揺擁曜楊様洋溶'
    '熔用窯羊耀葉蓉要謡踊遥陽養慾抑欲沃浴翌翼淀羅螺裸来莱頼雷洛絡落酪乱卵嵐欄濫藍蘭覧利吏履李梨理璃痢裏裡里離陸律率立葎掠略劉流溜琉留'
    '硫粒隆竜龍侶慮旅虜了亮僚両凌寮料梁涼猟療瞭稜糧良諒遼量陵領力緑倫厘林淋燐琳臨輪隣鱗麟瑠塁涙累類令伶例冷励嶺怜玲礼苓鈴隷零霊麗齢暦'
    '歴列劣烈裂廉恋憐漣煉簾練聯蓮連錬呂魯櫓炉賂路露労婁廊弄朗楼榔浪漏牢狼篭老聾蝋郎六麓禄肋録論倭和話歪賄脇惑枠鷲亙亘鰐詫藁蕨椀湾碗腕'
    '─№丼侘僭儂凛剌卍吼咎呟咆咤哮哭唸嗚嗜嘲囁囮坩埒堝墟壺奢媚屁屓巫帛廣悸慇憑憫懃懺抉拗拿拉捩揉撻擲攣暈曖曰朦朧檻鬱殲滲炸焉煌熾爬狡'
    '猾瑣璧瞞疼痒痙痺癪眩睨瞑磔祟祓稟簪絆綺緻辮罠羞腑舐苺萬薔薇蠱裔訛訝誅諍賽贄贅贔跪踵躇躊躾逞邏鉈闊隕雉勒靱頷騙渾峙摯愕埃傲遽僥蠢虔'
    '袂徘徊儚轢冤佛濤Ⅱ傀會趙餃魄謳貂棗ⅩⅠ圓穹翔嗅蚤楯匣煥遙爛棘刳弖號國鯱韋滸栞魏Ⅳ眞靡霙檜羯渕蝙泪黴茉莉珈譚〓〓〓〓〓〓〓〓〓〓〓'
    '〓〓'
)

MSG_START = 0xFF65        # normal dialogue
MSG_START_ALT = 0xFF37    # event / mini-game text (no speaker)
MSG_TEXT = 0xFFF0
NAME_END = 0xFFFF
NEWLINE = 0xFFFE
MSG_END = 0xFFFB
MENU_START = 0xFFFD
MENU_CHOICES = 0xFFFC


def glyphs_to_text(values):
    return ''.join(GLYPHS[v] if v < len(GLYPHS) else '{%04X}' % v for v in values)


def parse_script(data):
    """Yield ('message', msg_id, speaker, text) or ('menu', None, None, [(choice, target), ...])."""
    words = struct.unpack('<%dH' % (len(data) // 2), data[:len(data) // 2 * 2])
    i = 0
    while i < len(words) - 4:
        if (words[i] == MSG_TEXT and i >= 3 and words[i - 3] in (MSG_START, MSG_START_ALT)
                and words[i + 1] < 0x8000):
            msg_id = words[i + 1]
            j = i + 2
            body = []
            # text ends at the first control word other than line break / speaker separator
            while j < len(words) and (words[j] < 0xFF00 or words[j] in (NEWLINE, NAME_END)):
                body.append(words[j])
                j += 1
            speaker = ''
            if NAME_END in body:
                cut = body.index(NAME_END)
                speaker, body = glyphs_to_text(body[:cut]), body[cut + 1:]
            lines, current = [], []
            for v in body:
                if v == NEWLINE:
                    lines.append(current)
                    current = []
                else:
                    current.append(v)
            lines.append(current)
            text = '\n'.join(glyphs_to_text(line) for line in lines).strip('\n')
            yield 'message', msg_id, speaker, text
            i = j
        elif (words[i] == MENU_CHOICES and i >= 3 and words[i - 3] == MENU_START
              and i + 1 < len(words) and words[i + 1] == NAME_END):
            j = i + 2
            choices = []
            while j < len(words):
                end = j
                while end < len(words) and words[end] != NAME_END:
                    end += 1
                if end == j or end + 2 >= len(words):   # empty entry = end of menu
                    break
                label, target = words[j:end], words[end + 2]
                if any(v >= len(GLYPHS) for v in label) or target >= 0x1000:
                    choices = []                         # not a real menu
                    break
                choices.append((glyphs_to_text(label), target))
                j = end + 3
            if choices:
                yield 'menu', None, None, choices
            i = j + 1
        else:
            i += 1


def format_script(data):
    out = []
    format_script.count = 0
    for kind, msg_id, speaker, text in parse_script(data):
        if kind == 'menu':
            out.append('\n'.join('  > %s  (-> %d)' % choice for choice in text))
            continue
        format_script.count += 1
        header = ('%04d %s' % (msg_id, speaker)) if speaker else '%04d' % msg_id
        out.append(header + '\n' + text)
    return '\n\n'.join(out)


def is_quiz(data):
    if len(data) < 8:
        return False
    first = struct.unpack_from('<I', data, 0)[0]
    if first % 4 or not 8 <= first < len(data):
        return False
    return struct.unpack_from('<2H', data, first) == (MENU_CHOICES, MSG_TEXT)


def split_lines(values):
    lines, current = [], []
    for v in values:
        if v == NEWLINE:
            lines.append(glyphs_to_text(current))
            current = []
        else:
            current.append(v)
    lines.append(glyphs_to_text(current))
    return [line for line in lines if line]


def format_quiz(data):
    count = struct.unpack_from('<I', data, 0)[0] // 4
    offsets = list(struct.unpack_from('<%dI' % count, data, 0)) + [len(data)]
    out = []
    for index in range(count):
        start, end = offsets[index], offsets[index + 1]
        words = list(struct.unpack_from('<%dH' % ((end - start) // 2), data, start))
        parts = []                              # (label, body) for question then answers
        i = 0
        while i < len(words) and words[i] != NAME_END or not parts and i < len(words):
            if words[i] == MSG_TEXT:
                label_start = i + 2             # skip FFF0 <id>
                sep = words.index(NAME_END, label_start)
                body_end = words.index(MSG_END, sep) if MSG_END in words[sep:] else len(words)
                parts.append((words[label_start:sep], words[sep + 1:body_end]))
                i = body_end + 1
            else:
                i += 1
        if not parts:
            continue
        label = glyphs_to_text(parts[0][0])
        question = '\n'.join(split_lines(parts[0][1]))
        answers = split_lines(parts[1][1]) if len(parts) > 1 else []
        block = 'Q%04d%s\n%s' % (index + 1, (' [%s]' % label) if label else '', question)
        if answers:
            block += '\n' + '\n'.join('  %s %s' % ('*' if k == 0 else '-', a) for k, a in enumerate(answers))
        if index // QUIZ_CATEGORY_SIZE == QUIZ_VOICE_CATEGORY:
            block += '\n  (voice: union %05d)' % (QUIZ_VOICES_FIRST + index % QUIZ_CATEGORY_SIZE)
        out.append(block)
    format_quiz.count = len(out)
    return '\n\n'.join(out)


def convert(data):
    """Return (text, number_of_entries) for a script or the quiz file."""
    if is_quiz(data):
        text = format_quiz(data)
        return text, format_quiz.count
    text = format_script(data)
    return text, format_script.count



VOICE_CMD = 0xFF65      # FF65 <msg_id> <character_id> [FFF0 <msg_id> speaker FFFF text...]
FILENAME_FORBIDDEN = '<>:"/\\|?*'


def voiced_lines(data, glyphs):
    """[(msg_id, character_id, speaker, text)] for every FF65 command, in file order."""
    words = struct.unpack('<%dH' % (len(data) // 2), data[:len(data) // 2 * 2])

    def to_text(values):
        return ''.join(glyphs[v] if v < len(glyphs) else '' for v in values)

    lines = []
    for i in range(len(words) - 3):
        if words[i] != VOICE_CMD:
            continue
        msg_id, character = words[i + 1], words[i + 2]
        speaker = text = ''
        if words[i + 3] == MSG_TEXT:                 # voice with a text box
            j = i + 5
            body = []
            while j < len(words) and (words[j] < 0xFF00 or words[j] in (NEWLINE, NAME_END)):
                body.append(words[j])
                j += 1
            if NAME_END in body:
                cut = body.index(NAME_END)
                speaker, body = to_text(body[:cut]), body[cut + 1:]
            parts, current = [], []
            for v in body:
                if v == NEWLINE:
                    parts.append(current)
                    current = []
                else:
                    current.append(v)
            parts.append(current)
            text = ' / '.join(to_text(p) for p in parts if p)
        lines.append((msg_id, character, speaker, text))  # no text box: voice-only line
    return lines


def safe_name(name):
    return ''.join('_' if c in FILENAME_FORBIDDEN or ord(c) < 32 else c for c in name)


def build_voice_names(sc_path):
    """Return {voice_id: (file_stem, csv_row)} computed from sc.cpk."""
    glyphs = GLYPHS
    scripts = read_scripts(sc_path)
    per_script = {stem: voiced_lines(scripts[stem], glyphs) for stem in BLOCK_ORDER}

    # main speaker of each character id, used to name voice-only lines
    speakers = {}
    for lines in per_script.values():
        for _, character, speaker, _ in lines:
            if speaker:
                speakers.setdefault(character, {}).setdefault(speaker, 0)
                speakers[character][speaker] += 1
    main_speaker = {c: max(s, key=s.get) for c, s in speakers.items()}

    names = {}
    voice_id = 0
    for stem in BLOCK_ORDER:
        for msg_id, character, speaker, text in per_script[stem]:
            shown = speaker or main_speaker.get(character, 'char%02d' % character)
            stem_name = 'sc%s_msg%04d_chr%02d_%s' % (stem, msg_id, character, safe_name(shown))
            names[voice_id] = (stem_name, [stem, msg_id, character, speaker, text])
            voice_id += 1
    return names


def read_scripts(sc_path):
    """Return {script stem: decompressed data} for every file of sc.cpk."""
    scripts = {}
    with open(sc_path, 'rb') as f:
        for name, offset, size in list_entries(f):
            f.seek(offset)
            data = f.read(size)
            if data[:8] == b'CRILAYLA':
                data = decompress_crilayla(data)
            scripts[os.path.splitext(name)[0]] = data
    return scripts
