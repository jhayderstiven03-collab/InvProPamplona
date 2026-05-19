from django.test import TransactionTestCase
from fastapi.testclient import TestClient
from api.main import app
from apps.inventory.models import Categoria, Producto
from apps.accounts.models import CustomUser
from django.db import connections

class APIEndpointTests(TransactionTestCase):
    def setUp(self):
        self.client = TestClient(app)
        
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
        # Cerrar todas las conexiones activas a la base de datos de prueba
        # para evitar el error 'database is being accessed by other users' al destruir la BD
        for conn in connections.all():
            conn.close()

    def test_obtener_productos(self):
        # Enviar petición GET al endpoint de productos
        response = self.client.get("/v1/productos/")
        self.assertEqual(response.status_code, 200)
        
        # Verificar que el producto de prueba esté en la respuesta
        data = response.json()
        self.assertTrue(len(data) >= 1)
        self.assertEqual(data[0]["nombre"], "Coca Cola")
        self.assertEqual(data[0]["sku"], "BEB-001")

    def test_obtener_categorias(self):
        # Enviar petición GET al endpoint de categorías
        response = self.client.get("/v1/categorias/")
        self.assertEqual(response.status_code, 200)
        
        # Verificar que la categoría de prueba esté en la respuesta
        data = response.json()
        self.assertTrue(len(data) >= 1)
        self.assertEqual(data[0]["nombre"], "Bebidas")

    def test_obtener_dashboard(self):
        # Enviar petición GET al dashboard sin autenticación
        # (Debería responder 200 con el comportamiento global de admin por defecto en fallback)
        response = self.client.get("/v1/dashboard/")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("total_productos", data)
        self.assertIn("entradas_hoy", data)
        self.assertIn("salidas_hoy", data)
        self.assertIn("alertas_activas", data)
        self.assertEqual(data["total_productos"], 1)

    def test_obtener_perfil_autorizado(self):
        # Enviar petición con el token mock del administrador de prueba
        headers = {"Authorization": f"Bearer mock_access_token_{self.admin_user.id}"}
        response = self.client.get("/v1/auth/perfil/", headers=headers)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["username"], "admin_test")
        self.assertEqual(data["rol"], "admin")
        self.assertIn("operaciones_hoy", data)
        self.assertIn("total_este_mes", data)
