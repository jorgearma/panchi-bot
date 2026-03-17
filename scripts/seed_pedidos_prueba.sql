  INSERT INTO pedidos (                                                                       
      ClienteID,                                                                              
      FechaCreacion,                                                                          
      Estado,                                                                                 
      Total,                                                      
      DireccionEntrega,
      TelefonoEntrega,                                                                        
      enlace,
      redisID,                                                                                
      estadopago,                                                 
      estadoauxiliar,
      forma_pago,                                                                             
      lat_entrega,
      lng_entrega                                                                             
  )                                                               
  SELECT TOP 1
      u.id,
      GETDATE(),
      N'pagado',
      12.50,
      u.direccion,
      REPLACE(u.numero_cliente, N'whatsapp:', N''),                                           
      NULL,
      NULL,                                                                                   
      N'SUCCEEDED',                                               
      NULL,
      N'online',
      NULL,
      NULL
  FROM usuarios u
  ORDER BY u.id;