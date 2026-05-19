from django.test import TransactionTestCase
from fastapi.testclient import TestClient
from api.main import app
from apps.inventory.models import Categoria, Producto
from apps.accounts.models import CustomUser
from django.db import connections

class APIEndpointTests(TransactionTestCase):
    def setUp(self):
        # Crear datos de prueba en la base de datos limpia de Django
        self.categoria = Categoria.objects.create(
            nombre="Bebidas",
            descripcion="Todo tipo de bebidas"
        )
        self.producto = Producto.objects.create(
            sku="BEB-001",
            nombre="Coca Cola",
            descripcion="Refresco de cola de 1L",
            stock_actual=10.0,
            stock_minimo=5.0,
            precio_unitario=1500.0,
            categoria=self.categoria
        )
        
        # Crear un usuario administrador de prueba
        self.admin_user = CustomUser.objects.create_user(
            username="admin_test",
            password="testpassword",
            rol="admin",
            nombre_completo="Admin Test",
            correo="admin@test.com"
        )

    def tearDown(self):
        # Forzar el cierre de todas las conexiones manejadas por Django
        connections.close_all()

    @classmethod
    def tearDownClass(cls):
        connections.close_all()
        super().tearDownClass()

    def test_obtener_productos(self):
        # Usar TestClient como context manager garantiza que se disparen
        # los eventos de apagado (shutdown) de FastAPI y se liberen hilos/conexiones.
        with TestClient(app) as client:
            response = client.get("/v1/productos/")
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            self.assertTrue(len(data) >= 1)
            self.assertEqual(data[0]["nombre"], "Coca Cola")
            self.assertEqual(data[0]["sku"], "BEB-001")

    def test_obtener_categorias(self):
        with TestClient(app) as client:
            response = client.get("/v1/categorias/")
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            self.assertTrue(len(data) >= 1)
            self.assertEqual(data[0]["nombre"], "Bebidas")

    def test_obtener_dashboard(self):
        with TestClient(app) as client:
            response = client.get("/v1/dashboard/")
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            self.assertIn("total_productos", data)
            self.assertIn("entradas_hoy", data)
            self.assertIn("salidas_hoy", data)
            self.assertIn("alertas_activas", data)
            self.assertEqual(data["total_productos"], 1)

    def test_obtener_perfil_autorizado(self):
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer mock_access_token_{self.admin_user.id}"}
            response = client.get("/v1/auth/perfil/", headers=headers)
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            self.assertEqual(data["username"], "admin_test")
            self.assertEqual(data["rol"], "admin")
            self.assertIn("operaciones_hoy", data)
            self.assertIn("total_este_mes", data)
