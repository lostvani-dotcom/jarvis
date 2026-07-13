"""
visao/faces.py
================
Detecção facial via Haar Cascade do próprio OpenCV (não exige download
extra -- os arquivos `.xml` vêm empacotados com `opencv-python`).

Reconhecimento (identificar QUEM é o rosto, não só que há um rosto)
tem DOIS caminhos possíveis:

  1. **LBPH (`cv2.face`, via `opencv-contrib-python`)** -- caminho
     PADRÃO usado por `FaceRecognizerLBPH` abaixo. Não exige `dlib`
     nem compilador C++ (o motivo de reconhecimento facial nunca ter
     saído do papel antes) -- só o próprio OpenCV, que o projeto já
     usa pra detecção. Guarda uma pasta de fotos de rosto por pessoa
     em `data/faces/<nome>/` (nunca versionada, ver .gitignore -- são
     dados biométricos) e treina um `LBPHFaceRecognizer` em memória a
     partir delas. Menos preciso que redes neurais de verdade, mas
     honesto o bastante pra "quem é essa pessoa" num círculo pequeno
     de rostos conhecidos (família, poucos amigos).
  2. **`face_recognition`/`dlib`** (funções soltas no fim do arquivo,
     compatibilidade com código antigo) -- mais preciso, mas pesado e
     exige compilador C++ no Windows pra instalar `dlib`. Opcional,
     não é mais o caminho usado pelos comandos de chat (ver
     plugins/reconhecimento_facial.py).
"""

import os
import re

from logs.logger import get_logger

log = get_logger("visao")

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False

_FACES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "faces")
_TAMANHO_ROSTO = (200, 200)  # todo rosto salvo/comparado é normalizado pra esse tamanho
_LIMIAR_CONFIANCA_PADRAO = 75.0  # LBPH: MENOR = mais parecido; acima disso, "desconhecido"

_cascade = None
_CASCADE_ARQUIVO = "haarcascade_frontalface_default.xml"
_CASCADE_LOCAL_FALLBACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", _CASCADE_ARQUIVO)


def _get_cascade():
    """Carrega o Haar Cascade de detecção facial -- normalmente vem
    empacotado com o opencv-python (`cv2.data.haarcascades`), mas
    algumas versões (ex.: opencv-python/opencv-contrib-python 5.0.x)
    pararam de incluir os arquivos `.xml` no wheel. Quando isso
    acontece, usa a cópia própria em `visao/data/` (mesmo arquivo,
    baixado uma vez do repositório oficial do OpenCV) como fallback --
    sem isso, TODA detecção facial (não só o reconhecimento LBPH)
    quebrava silenciosamente com `cv2.error: !empty()`."""
    global _cascade
    if _cascade is None:
        caminho = cv2.data.haarcascades + _CASCADE_ARQUIVO
        if not os.path.isfile(caminho):
            caminho = _CASCADE_LOCAL_FALLBACK
        classificador = cv2.CascadeClassifier(caminho)
        if classificador.empty():
            raise RuntimeError(
                f"Não encontrei o Haar Cascade de detecção facial (tentei '{caminho}'). "
                "Reinstale opencv-contrib-python ou baixe manualmente o arquivo "
                "haarcascade_frontalface_default.xml para visao/data/."
            )
        _cascade = classificador
    return _cascade


def available() -> bool:
    return HAS_OPENCV


def detect_faces(frame) -> list:
    """Retorna lista de (x, y, largura, altura) para cada rosto detectado."""
    if not HAS_OPENCV:
        raise RuntimeError("Instale 'opencv-python' para detecção facial.")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detected = _get_cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    return [tuple(int(v) for v in f) for f in detected]


def recognize_available() -> bool:
    return HAS_FACE_RECOGNITION


def encode_known_face(image_path: str):
    if not HAS_FACE_RECOGNITION:
        raise RuntimeError("Instale 'face_recognition' para reconhecimento (identificação) facial.")
    image = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(image)
    return encodings[0] if encodings else None


def identify_faces(frame, known_encodings: dict, tolerance: float = 0.6) -> list:
    """known_encodings: {nome: encoding}. Retorna lista de nomes
    identificados (ou "desconhecido") para cada rosto no frame."""
    if not HAS_FACE_RECOGNITION:
        raise RuntimeError("Instale 'face_recognition' para reconhecimento (identificação) facial.")
    import cv2 as _cv2
    rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb)
    encodings = face_recognition.face_encodings(rgb, locations)

    names = []
    for encoding in encodings:
        matches = face_recognition.compare_faces(list(known_encodings.values()), encoding, tolerance=tolerance)
        name = "desconhecido"
        if True in matches:
            name = list(known_encodings.keys())[matches.index(True)]
        names.append(name)
    return names


# ============================================================
# Reconhecimento facial via LBPH (cv2.face) -- caminho padrão,
# usado por plugins/reconhecimento_facial.py. Ver docstring do
# módulo pra por que este é o caminho recomendado (sem dlib).
# ============================================================

def lbph_available() -> bool:
    return HAS_OPENCV and hasattr(cv2, "face")


def _nome_seguro(nome: str) -> str:
    """Normaliza um nome de pessoa pra um nome de pasta seguro no
    disco -- evita path traversal (`../../`) e caracteres inválidos em
    nomes de arquivo no Windows, sem impedir acentos/espaços no nome
    exibido de volta pro usuário (só na pasta em si)."""
    limpo = re.sub(r"[^\w\-áàâãéèêíïóôõöúçñÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇÑ ]", "", nome.strip())
    limpo = re.sub(r"\s+", "_", limpo).strip("_.")
    return limpo or "desconhecido"


def _pasta_pessoa(nome: str, faces_dir: str = None) -> str:
    return os.path.join(faces_dir or _FACES_DIR, _nome_seguro(nome))


def _maior_rosto(boxes: list):
    """Entre vários rostos detectados no mesmo frame, assume que o
    maior (mais próximo da câmera) é o alvo do cadastro/identificação
    principal -- suficiente pra uso pessoal (um rosto por vez na
    frente da câmera), sem precisar de UI pra escolher qual rosto."""
    if not boxes:
        return None
    return max(boxes, key=lambda b: b[2] * b[3])


def _extrair_rosto_cinza(frame, box):
    x, y, w, h = box
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    rosto = gray[max(0, y):y + h, max(0, x):x + w]
    if rosto.size == 0:
        return None
    rosto = cv2.resize(rosto, _TAMANHO_ROSTO)
    return cv2.equalizeHist(rosto)  # normaliza iluminação -- LBPH é sensível a isso


class FaceRecognizerLBPH:
    """Cadastro (várias fotos por pessoa, salvas em `data/faces/<nome>/`)
    + identificação (treina um `cv2.face.LBPHFaceRecognizer` em memória
    a partir dessas fotos). O treino é rápido o bastante (poucos
    milissegundos até algumas dezenas de fotos) pra refazer sob demanda
    em vez de persistir o modelo binário -- evita problema de
    compatibilidade do formato salvo entre versões do OpenCV."""

    def __init__(self, faces_dir: str = None):
        self.faces_dir = faces_dir or _FACES_DIR
        self._recognizer = None
        self._id_para_nome = {}
        self._treinado = False

    def available(self) -> bool:
        return lbph_available()

    def known_names(self) -> list:
        if not os.path.isdir(self.faces_dir):
            return []
        return sorted(
            d for d in os.listdir(self.faces_dir)
            if os.path.isdir(os.path.join(self.faces_dir, d)) and os.listdir(os.path.join(self.faces_dir, d))
        )

    def sample_count(self, nome: str) -> int:
        pasta = _pasta_pessoa(nome, self.faces_dir)
        if not os.path.isdir(pasta):
            return 0
        return len([f for f in os.listdir(pasta) if f.lower().endswith(".png")])

    def enroll_frames(self, nome: str, frames: list) -> int:
        """Detecta o maior rosto em cada frame e salva como amostra de
        `nome`. Retorna quantas amostras novas foram salvas de fato
        (frames sem rosto detectável são ignorados, não contam erro --
        é normal perder alguns frames de um burst de captura)."""
        if not self.available():
            raise RuntimeError("Instale 'opencv-contrib-python' para reconhecimento facial (LBPH).")
        pasta = _pasta_pessoa(nome, self.faces_dir)
        os.makedirs(pasta, exist_ok=True)
        proximo_indice = self.sample_count(nome)
        salvas = 0
        for frame in frames:
            box = _maior_rosto(detect_faces(frame))
            if box is None:
                continue
            rosto = _extrair_rosto_cinza(frame, box)
            if rosto is None:
                continue
            caminho = os.path.join(pasta, f"{proximo_indice + salvas:03d}.png")
            cv2.imwrite(caminho, rosto)
            salvas += 1
        if salvas:
            self._treinado = False  # invalida o cache -- próxima identificação retreina
        return salvas

    def forget(self, nome: str) -> bool:
        """Apaga todas as amostras de `nome`. Retorna False se a
        pessoa não tinha nada cadastrado."""
        pasta = _pasta_pessoa(nome, self.faces_dir)
        if not os.path.isdir(pasta):
            return False
        import shutil
        shutil.rmtree(pasta)
        self._treinado = False
        return True

    def _garantir_treinado(self):
        if self._treinado:
            return
        if not self.available():
            raise RuntimeError("Instale 'opencv-contrib-python' para reconhecimento facial (LBPH).")

        imagens, rotulos = [], []
        self._id_para_nome = {}
        for indice, nome in enumerate(self.known_names()):
            self._id_para_nome[indice] = nome
            pasta = _pasta_pessoa(nome, self.faces_dir)
            for arquivo in sorted(os.listdir(pasta)):
                if not arquivo.lower().endswith(".png"):
                    continue
                img = cv2.imread(os.path.join(pasta, arquivo), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                imagens.append(img)
                rotulos.append(indice)

        self._recognizer = cv2.face.LBPHFaceRecognizer_create()
        if imagens:
            import numpy as np
            self._recognizer.train(imagens, np.array(rotulos))
        self._treinado = True

    def identify(self, frame, limiar_confianca: float = _LIMIAR_CONFIANCA_PADRAO) -> list:
        """Retorna uma lista de {"nome", "confianca", "caixa"} -- um
        item por rosto detectado no frame. "nome" vem "desconhecido"
        quando ninguém cadastrado bate (confiança acima do limiar) OU
        quando ainda não há ninguém cadastrado."""
        if not self.available():
            raise RuntimeError("Instale 'opencv-contrib-python' para reconhecimento facial (LBPH).")
        self._garantir_treinado()

        resultados = []
        for box in detect_faces(frame):
            rosto = _extrair_rosto_cinza(frame, box)
            if rosto is None:
                continue
            nome = "desconhecido"
            confianca = None
            if self._id_para_nome:
                indice, confianca = self._recognizer.predict(rosto)
                if confianca <= limiar_confianca:
                    nome = self._id_para_nome.get(indice, "desconhecido")
            resultados.append({"nome": nome, "confianca": confianca, "caixa": box})
        return resultados


_recognizer_padrao = None


def get_recognizer() -> FaceRecognizerLBPH:
    """Instância compartilhada -- reaproveita o modelo treinado em
    memória entre chamadas na mesma execução do Ultron, em vez de
    retreinar do zero a cada comando de chat."""
    global _recognizer_padrao
    if _recognizer_padrao is None:
        _recognizer_padrao = FaceRecognizerLBPH()
    return _recognizer_padrao
