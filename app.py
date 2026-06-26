import streamlit as st
import rdflib
from openai import OpenAI

# --- 1. ARAYÜZ AYARLARI ---
st.set_page_config(page_title="Movie KG Chatbot", page_icon="🎬")
st.title("🎬 Semantik Film Bilgi Grafiği Asistanı")

# --- 2. BİLGİ GRAFİĞİNİ YÜKLE ---
@st.cache_resource
def load_knowledge_graph():
    g = rdflib.Graph()
    # Tüm TTL dosyalarını yüklüyoruz
    g.parse("movie_tbox_v2.ttl", format="turtle")
    g.parse("abox_v2.ttl", format="turtle")
    g.parse("movie_abox_aligned.ttl", format="turtle")
    g.parse("movie_abox_scifi.ttl", format="turtle")
    return g

g = load_knowledge_graph()

# --- 3. İSTEM MÜHENDİSLİĞİ (PROMPT) ---
system_prompt = """
Sen uzman bir Semantic Web asistanısın. Görevin SADECE geçerli SPARQL sorguları yazmaktır.

Kullanman GEREKEN ontoloji yapısı aşağıdadır:
PREFIX schema: <http://schema.org/>
PREFIX inst: <https://www.example.org/movie/instances#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>

İZİN VERİLEN ÖZELLİKLER (PROPERTIES):
- schema:name (Film, kişi veya platform adı)
- schema:actor (Film oyuncu bağlantısı)
- schema:director (Film yönetmen bağlantısı)
- inst:availableOnPlatform (Film platform bağlantısı)
- foaf:name (Kişi adı)

KESİN KURALLAR:
1. SADECE SPARQL kodunu döndür. Başında veya sonunda hiçbir açıklama yapma.
2. SELECT kısmında istediğin değişkeni mutlaka WHERE içinde tanımla!
3. İsim aramalarında tam eşleşme ASLA yapma! DAİMA WHERE bloğunda tanımladığın değişken adını filtrele. (Örnek: ?actor foaf:name ?actorName . FILTER(CONTAINS(LCASE(?actorName), "kelime"))). Asla kodda olmayan bir değişken ismi kullanma.
4. "Veya" mantığı için ASLA 'OR' kullanma, DAİMA tek FILTER içinde '||' kullan.
5. "Kimlerle çalıştı" veya "Rol arkadaşları" gibi sorularda DAİMA aranan kişinin kendisini sonuçlardan çıkarmak için FILTER(?actor != ?coActor) mantığını kullan.

ÖRNEK 1: Netflix'te veya Amazon'da hangi filmler var?
PREFIX schema: <http://schema.org/>
PREFIX inst: <https://www.example.org/movie/instances#>
SELECT DISTINCT ?movieName WHERE {
  ?movie inst:availableOnPlatform ?platform .
  ?platform schema:name ?platformName .
  FILTER(CONTAINS(LCASE(?platformName), "netflix") || CONTAINS(LCASE(?platformName), "amazon"))
  ?movie schema:name ?movieName .
}

ÖRNEK 2: Cillian Murphy veya Zendaya hangi filmde oynadı?
PREFIX schema: <http://schema.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
SELECT DISTINCT ?movieName WHERE {
  ?actor foaf:name ?actorName .
  FILTER(CONTAINS(LCASE(?actorName), "cillian") || CONTAINS(LCASE(?actorName), "zendaya"))
  { ?movie schema:actor ?actor . } UNION { ?movie schema:actor ?role . ?role schema:actor ?actor . }
  ?movie schema:name ?movieName .
}

ÖRNEK 3: Kullanıcı sadece film adı yazarsa (Örn: The Matrix, Dune) genel bilgileri getir:
PREFIX schema: <http://schema.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
SELECT DISTINCT ?movieName ?actorName WHERE {
  ?movie schema:name ?movieName .
  FILTER(CONTAINS(LCASE(?movieName), "matrix") || CONTAINS(LCASE(?movieName), "dune"))
  OPTIONAL {
    { ?movie schema:actor ?actor . } UNION { ?movie schema:actor ?role . ?role schema:actor ?actor . }
    ?actor foaf:name ?actorName .
  }
}

ÖRNEK 4: Brad Pitt kimlerle çalıştı? (Rol arkadaşları)
PREFIX schema: <http://schema.org/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
SELECT DISTINCT ?coActorName ?movieName WHERE {
  ?actor foaf:name ?actorName .
  FILTER(CONTAINS(LCASE(?actorName), "brad"))
  
  { ?movie schema:actor ?actor . } UNION { ?movie schema:actor ?role1 . ?role1 schema:actor ?actor . }
  { ?movie schema:actor ?coActor . } UNION { ?movie schema:actor ?role2 . ?role2 schema:actor ?coActor . }
  
  ?coActor foaf:name ?coActorName .
  FILTER(?actor != ?coActor)
  ?movie schema:name ?movieName .
}
"""

def extract_pure_sparql(raw_text):
    start_idx = raw_text.find("PREFIX")
    if start_idx == -1:
        start_idx = raw_text.find("SELECT")
        
    end_idx = raw_text.rfind("}")
    
    if start_idx != -1 and end_idx != -1:
        query = raw_text[start_idx:end_idx+1]
        
        # --- LLM HATA DÜZELTİCİ (SAFETY NET) ---
        query = query.replace(" OR ", " || ").replace(" AND ", " && ")
        # ---------------------------------------
        
        return query
    return raw_text
def ask_llm_for_sparql(user_question, client):
    response = client.chat.completions.create(
        model="llama3",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Soru: '{user_question}' için SPARQL yaz."}
        ]
    )
    raw_query = response.choices[0].message.content.strip()
    return extract_pure_sparql(raw_query)

def generate_natural_answer(user_question, graph_results, client):
    response = client.chat.completions.create(
        model="llama3", 
        messages=[
            {"role": "system", "content": "Sen grafikten gelen ham verileri okuyup kullanıcıya Türkçe akıcı ve kısa cevap veren bir asistansın. Grafikte olmayan hiçbir bilgiyi kafandan uydurma.Cevabını SADECE Türkçe ver, başka dil kullanma"},
            {"role": "user", "content": f"Soru: {user_question}\nGrafik Verisi: {graph_results}\nLütfen bu veriye dayanarak soruyu yanıtla."}
        ]
    )
    return response.choices[0].message.content

# --- 4. SOHBET UYGULAMASI ---
user_query = st.text_input("Filmler, oyuncular veya platformlar hakkında bir soru sorun:")

if st.button("Sor"):
    if user_query:
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        
        with st.spinner("Lokal Yapay Zeka Veritabanını Tarıyor..."):
            try:
                sparql_query = ask_llm_for_sparql(user_query, client)
                st.code(sparql_query, language="sparql")
                
                results = g.query(sparql_query)
                raw_data = [str(row) for row in results]
                
                if raw_data:
                    final_answer = generate_natural_answer(user_query, raw_data, client)
                    st.success(final_answer)
                else:
                    st.warning("Bilgi grafiğinde bu soruya uygun bir veri bulunamadı.")
            except Exception as e:
                st.error(f"Sorgu çalıştırılırken bir hata oluştu: {e}")