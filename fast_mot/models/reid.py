from pathlib import Path
import tensorrt as trt


class ReID:
    PATH = None
    ONNX_PATH = None
    INPUT_SHAPE = None
    OUTPUT_LAYOUT = None
    METRIC = None

    @classmethod
    def build_engine(cls, trt_logger, batch_size):
        def round_up(n):
            return n if n & (n - 1) == 0 else 1 << int.bit_length(n)
        
        if isinstance(batch_size, int):
            dynamic_batch_opts = [batch_size]
        else:
            dynamic_batch_opts = batch_size

        EXPLICIT_BATCH = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
        with trt.Builder(trt_logger) as builder, builder.create_network(EXPLICIT_BATCH) as network, \
            trt.OnnxParser(network, trt_logger) as parser:

            dynamic_batch_opts = [round_up(batch_size) for batch_size in dynamic_batch_opts]
            print('Building engine with batch options:', dynamic_batch_opts)
            print('This may take a while...')

            # Parse model file
            with open(cls.ONNX_PATH, 'rb') as model_file:
                parser.parse(model_file.read())

            # Create optimization profiles for the batch options
            config = builder.create_builder_config()
            config.max_workspace_size = 1 << 30
            if builder.platform_has_fast_fp16:
                config.flags = 1 << int(trt.BuilderFlag.FP16)
            for batch_size in dynamic_batch_opts:
                profile = builder.create_optimization_profile()
                batch_shape = (batch_size, *cls.INPUT_SHAPE)
                profile.set_shape(network.get_input(0).name, batch_shape, batch_shape, batch_shape) 
                config.add_optimization_profile(profile)
            
            # Reshape input batch size for static model
            if len(dynamic_batch_opts) == 1 and network.get_input(0).shape[0] != -1:
                network.get_input(0).shape = [batch_size, *cls.INPUT_SHAPE]

            engine = builder.build_engine(network, config)
            if engine is None:
                return None
            print("Completed creating Engine")
            with open(cls.PATH, "wb") as f:
                f.write(engine.serialize())
            return engine


class OSNetAIN(ReID):
    PATH = Path(__file__).parent / 'osnet_ain_x1_0_msmt17.trt'
    ONNX_PATH = Path(__file__).parent / 'osnet_ain_x1_0_msmt17' / 'osnet_ain_x1_0_32.onnx'
    INPUT_SHAPE = (3, 256, 128)
    OUTPUT_LAYOUT = 512
    METRIC = 'cosine'


class OSNet025(ReID):
    PATH = Path(__file__).parent / 'osnet_x0_25_msmt17.trt'
    ONNX_PATH = Path(__file__).parent / 'osnet_x0_25_msmt17' / 'osnet_x0_25_dynamic.onnx'
    INPUT_SHAPE = (3, 256, 128)
    OUTPUT_LAYOUT = 512
    METRIC = 'euclidean'


# trt_logger = trt.Logger(trt.Logger.VERBOSE)
# trt.init_libnvinfer_plugins(trt_logger, '')
# OSNet025.build_engine(trt_logger, 32)

# runtime = trt.Runtime(trt_logger)
# with open(OSNet025.PATH, 'rb') as engine_file:
#     buf = engine_file.read()
#     engine = runtime.deserialize_cuda_engine(buf)
#     print(engine.max_batch_size)
