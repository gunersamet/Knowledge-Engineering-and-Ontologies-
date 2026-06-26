import rdflib
from pyshacl import validate

print("Grafikler yükleniyor...")

# 1. TBox ve ABox verilerimizi içeren ana grafiği (Data Graph) oluşturuyoruz
data_graph = rdflib.Graph()
data_graph.parse("movie_tbox_v2.ttl", format="turtle")
data_graph.parse("abox_v2.ttl", format="turtle")

# 2. Yazdığımız SHACL kurallarını içeren grafiği (Shapes Graph) oluşturuyoruz
shapes_graph = rdflib.Graph()
shapes_graph.parse("shacl_shapes.ttl", format="turtle")

print("SHACL doğrulaması başlatılıyor. Lütfen bekleyin...\n")

# 3. Doğrulama işlemini çalıştırıyoruz
conforms, results_graph, results_text = validate(
    data_graph,
    shacl_graph=shapes_graph,
    data_graph_format="turtle",
    shacl_graph_format="turtle",
    inference='rdfs',
    debug=False,
    serialize_report_graph=True
)

# 4. Sonuçları ekrana basıyoruz
print("-" * 40)
if conforms:
    print("✅ TEBRİKLER! Verileriniz SHACL kurallarıyla %100 uyumlu (HATA YOK).")
else:
    print("❌ DİKKAT! Verilerinizde hatalar bulundu. Detaylar aşağıdadır:\n")
    print(results_text)
print("-" * 40)